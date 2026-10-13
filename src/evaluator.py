"""
Evaluator — ядро оценки.

Принимает список кейсов, список моделей (LLMClient), прогоняет
каждый кейс через каждую модель, вычисляет метрики и агрегирует
их в лидерборд.

Реализованы T1, T2 и T3. Каждый таск добавляет билдер промпта в PROMPT_BUILDERS
и scorer с сигнатурой `(case, prediction) -> CaseResult` в SCORERS.
"""

from __future__ import annotations

import ast
import difflib
import textwrap
import uuid
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from .harness import LLMClient, parse_t1_output
from .schema import BenchCase, CaseResult, Prediction
from .sandbox import DockerSandbox
from .tasks import task1_lint, task2_security, task3_refactor



# ---------------------------------------------------------------------------
# Мягкие метрики (замена бинарному Exact Match).
#
# Exact Match наказывает модель за лишний пробел и другие кавычки. Два
# дешёвых способа этого не делать, оба на стдлиб:
#   fix_similarity — символьное сходство (роль CodeBLEU-lite);
#   ast_match      — совпадение AST, т.е. фикс эквивалентен эталону.
# ---------------------------------------------------------------------------


def _ast_key(fix: str) -> str | None:
    """AST-отпечаток строки фикса. None — если фрагмент вообще не парсится."""
    src = textwrap.dedent(fix).strip()
    if not src:
        return ""  # пустой фикс ("удалить строку") — тоже валидный ответ
    # Строка фикса — это фрагмент, а не готовый модуль. Пробуем достроить его
    # до парсящегося кода: как есть -> дописать тело -> обернуть в try
    # (`except ...:` сам по себе не парсится вообще никак).
    candidates = (src, f"{src}\n    pass", f"try:\n    pass\n{src}\n    pass")
    for candidate in candidates:
        try:
            return ast.dump(ast.parse(candidate))
        except SyntaxError:
            continue
    return None


def soft_metrics(pred_fix: str, gold_fix: str) -> dict[str, float]:
    """fix_similarity всегда, ast_match — только если оба фикса распарсились."""
    pred, gold = pred_fix.strip(), gold_fix.strip()
    metrics = {"fix_similarity": difflib.SequenceMatcher(None, pred, gold).ratio()}
    pred_key, gold_key = _ast_key(pred), _ast_key(gold)
    if pred_key is not None and gold_key is not None:
        metrics["ast_match"] = float(pred_key == gold_key)
    return metrics


Scorer = Callable[[BenchCase, Prediction], CaseResult]


def score_t1(case: BenchCase, pred: Prediction) -> CaseResult:

    parsed = parse_t1_output(pred.raw_output)
    pred.parsed = parsed

    type_correct = parsed["error_type"] == case.expected["error_type"]
    fix_correct = parsed["fix"].strip() == case.expected["fix"].strip()

    multiple_valid = bool(case.metadata.get("multiple_valid", False))

    metrics: dict[str, float] = {"type_accuracy": float(type_correct)}
    metrics.update(soft_metrics(parsed["fix"], case.expected["fix"]))
    if not multiple_valid:
        metrics["exact_match"] = float(fix_correct)

    # ast_match закрывает косметические расхождения (пробелы, кавычки):
    # семантически тот же фикс больше не считается ошибкой.
    ast_equal = bool(metrics.get("ast_match", 0.0))
    passed = type_correct and (fix_correct or ast_equal or multiple_valid)

    return CaseResult(
        case_id=case.case_id,
        model_name=pred.model_name,
        task=case.task,
        metrics=metrics,
        passed=passed,
    )


def score_t2(case: BenchCase, pred: Prediction) -> CaseResult:
    """Метрики Task 2: Precision/Recall/F1 по строкам + верность CWE.

    CWE засчитывается, если совпал с эталоном или с одной из альтернатив
    в metadata.acceptable_cwe. Кейс пройден, если CWE верный, найдены все
    строки с багом и хотя бы половина названных строк — действительно баг
    (иначе модель могла бы «пройти», перечислив все строки подряд).
    """
    parsed = task2_security.parse_t2_output(pred.raw_output)
    pred.parsed = parsed

    gold_lines = set(case.expected["lines"])
    pred_lines = set(parsed["lines"])
    hit = len(gold_lines & pred_lines)
    precision = hit / len(pred_lines) if pred_lines else 0.0
    recall = hit / len(gold_lines)
    f1 = 2 * precision * recall / (precision + recall) if hit else 0.0

    gold_cwe = case.expected["cwe"]
    accepted = {gold_cwe, *case.metadata.get("acceptable_cwe", [])}
    cwe_ok = parsed["cwe"] in accepted

    return CaseResult(
        case_id=case.case_id,
        model_name=pred.model_name,
        task=case.task,
        metrics={
            "line_precision": precision,
            "line_recall": recall,
            "line_f1": f1,
            "cwe_accuracy": float(cwe_ok),
        },
        passed=cwe_ok and recall == 1.0 and precision >= 0.5,
        # Допустимая альтернатива считается тем же классом, что и эталон.
        labels={"gold": gold_cwe, "pred": gold_cwe if cwe_ok else (parsed["cwe"] or "NONE")},
    )


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    """Macro-F1 по классам: F1 считается для каждого класса отдельно и
    усредняется без весов, поэтому редкие CWE весят столько же, сколько
    частые. Классы — объединение эталонных и предсказанных (как в sklearn)."""
    classes = {g for g, _ in pairs} | {p for _, p in pairs}
    scores = []
    for c in classes:
        tp = sum(1 for g, p in pairs if g == c and p == c)
        fp = sum(1 for g, p in pairs if g != c and p == c)
        fn = sum(1 for g, p in pairs if g == c and p != c)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return mean(scores) if scores else 0.0


# Песочница для T3. Создаётся при первом использовании; тесты могут
# подменить её заглушкой, чтобы не требовать Docker.
T3_SANDBOX: DockerSandbox | None = None


def _sandbox() -> DockerSandbox:
    global T3_SANDBOX
    if T3_SANDBOX is None:
        T3_SANDBOX = DockerSandbox()
    return T3_SANDBOX


def score_t3(case: BenchCase, pred: Prediction) -> CaseResult:
    """Метрики Task 3 по заданию: unit-тесты + снижение сложности.

    Код модели вместе с тестами кейса запускается в Docker-песочнице.
    Кейс засчитан, если тесты прошли и код стал проще: ни число строк, ни
    число узлов AST не выросли, и хотя бы одно уменьшилось.
    Снижение сложности (LOC↓, AST↓) учитывается только для кейсов с
    пройденными тестами: «упростить» код, сломав его, — не заслуга.
    """
    code = task3_refactor.extract_code(pred.raw_output)
    pred.parsed = {"code": code}
    before = task3_refactor.code_metrics(case.metadata["snippet"])
    after = task3_refactor.code_metrics(code) if code else None

    tests_ok = False
    if after is not None:  # непарсящийся код незачем запускать
        nonce = uuid.uuid4().hex
        script = task3_refactor.build_test_script(code, case.metadata["tests"], nonce)
        result = _sandbox().run(script)
        tests_ok = result.ok and nonce in result.stdout

    metrics: dict[str, float] = {"tests_pass": float(tests_ok)}
    simpler = False
    if tests_ok:
        metrics["loc_reduction"] = (before["loc"] - after["loc"]) / before["loc"]
        metrics["ast_reduction"] = (before["ast_nodes"] - after["ast_nodes"]) / before["ast_nodes"]
        simpler = task3_refactor.is_simpler(before, after)

    return CaseResult(
        case_id=case.case_id,
        model_name=pred.model_name,
        task=case.task,
        metrics=metrics,
        passed=tests_ok and simpler,
    )


SCORERS: dict[str, Scorer] = {"T1": score_t1, "T2": score_t2, "T3": score_t3}

PROMPT_BUILDERS: dict[str, Callable[..., str]] = {
    "T1": task1_lint.build_prompt,
    "T2": task2_security.build_prompt,
    "T3": task3_refactor.build_prompt,
}


@dataclass
class LeaderboardRow:
    model_name: str
    task: str
    n_cases: int
    metrics: dict[str, float] = field(default_factory=dict)
    avg_latency_ms: float = 0.0


def run(cases: list[BenchCase], models: list[LLMClient]) -> list[LeaderboardRow]:
    """Прогоняет все кейсы через все модели и возвращает лидерборд."""
    rows: list[LeaderboardRow] = []
    for model in models:
        per_task: dict[str, list[CaseResult]] = {}
        latencies: dict[str, list[float]] = {}
        for case in cases:
            scorer = SCORERS.get(case.task)
            if scorer is None:
                continue  # таск ещё не реализован — не тратим запрос к модели
            prompt = PROMPT_BUILDERS[case.task](case, include_oracle=model.needs_oracle)
            pred = model.predict(case.case_id, prompt)
            result = scorer(case, pred)
            per_task.setdefault(case.task, []).append(result)
            latencies.setdefault(case.task, []).append(pred.latency_ms)

        for task, results in per_task.items():
            agg: dict[str, float] = {}
            # собираем все ключи из всех результатов, а не только из первого
            all_keys: set[str] = set()
            for r in results:
                all_keys.update(r.metrics.keys())
            for k in all_keys:
                values = [r.metrics[k] for r in results if k in r.metrics]
                if values:
                    agg[k] = mean(values)
            agg["pass_rate"] = mean(float(r.passed) for r in results)
            pairs = [(r.labels["gold"], r.labels["pred"]) for r in results if r.labels]
            if pairs:
                agg["cwe_macro_f1"] = macro_f1(pairs)
            rows.append(
                LeaderboardRow(
                    model_name=model.name,
                    task=task,
                    n_cases=len(results),
                    metrics=agg,
                    avg_latency_ms=mean(latencies[task]),
                )
            )
    return rows


# Колонки лидерборда по таскам: (заголовок, ключ метрики, ширина).
TASK_COLUMNS: dict[str, list[tuple[str, str, int]]] = {
    "T1": [("EM", "exact_match", 7), ("AST", "ast_match", 7), ("Sim", "fix_similarity", 7),
           ("TypeAcc", "type_accuracy", 8)],
    "T2": [("LineP", "line_precision", 7), ("LineR", "line_recall", 7),
           ("LineF1", "line_f1", 7), ("CWE-Acc", "cwe_accuracy", 8),
           ("CWE-F1", "cwe_macro_f1", 7)],
    "T3": [("Tests", "tests_pass", 7), ("LOC↓", "loc_reduction", 7),
           ("AST↓", "ast_reduction", 7)],
}


def format_leaderboard(rows: list[LeaderboardRow]) -> str:
    """Текстовый лидерборд: по таблице на таск, внутри — по убыванию Pass."""
    if not rows:
        return "(нет результатов)"
    blocks = []
    for task in sorted({r.task for r in rows}):
        cols = TASK_COLUMNS.get(task, [])
        header = f"{'model':<24} {'task':<5} {'n':>4}  "
        header += "".join(f"{title:>{width}} " for title, _, width in cols)
        header += f"{'Pass':>7}  {'lat(ms)':>8}"
        lines = [header, "-" * len(header)]
        task_rows = [r for r in rows if r.task == task]
        for r in sorted(task_rows, key=lambda x: -x.metrics.get("pass_rate", 0)):
            line = f"{r.model_name:<24} {r.task:<5} {r.n_cases:>4}  "
            line += "".join(
                f"{r.metrics.get(key, 0):>{width}.2%} " for _, key, width in cols
            )
            line += f"{r.metrics.get('pass_rate', 0):>7.2%}  {r.avg_latency_ms:>8.2f}"
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
