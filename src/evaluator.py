"""
Evaluator — ядро оценки.

Принимает список кейсов, список моделей (LLMClient), прогоняет
каждый кейс через каждую модель, вычисляет метрики и агрегирует
их в лидерборд.

Пока реализован только T1. Каждый следующий таск добавляет свою
функцию scorer'а с сигнатурой `(case, prediction) -> CaseResult`.
"""

from __future__ import annotations

import ast
import difflib
import textwrap
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from .harness import LLMClient, parse_t1_output
from .schema import BenchCase, CaseResult, Prediction
from .tasks.task1_lint import build_prompt



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


SCORERS: dict[str, Scorer] = {"T1": score_t1}


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
            prompt = build_prompt(case, include_oracle=model.needs_oracle)
            pred = model.predict(case.case_id, prompt)
            scorer = SCORERS.get(case.task)
            if scorer is None:
                continue
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


def format_leaderboard(rows: list[LeaderboardRow]) -> str:
    """Простой текстовый вывод лидерборда."""
    if not rows:
        return "(нет результатов)"
    lines = [
        f"{'model':<24} {'task':<5} {'n':>4}  {'EM':>7} {'AST':>7} {'Sim':>7} "
        f"{'TypeAcc':>8} {'Pass':>7}  {'lat(ms)':>8}"
    ]
    lines.append("-" * len(lines[0]))
    for r in sorted(rows, key=lambda x: -x.metrics.get("pass_rate", 0)):
        lines.append(
            f"{r.model_name:<24} {r.task:<5} {r.n_cases:>4}  "
            f"{r.metrics.get('exact_match', 0):>7.2%} "
            f"{r.metrics.get('ast_match', 0):>7.2%} "
            f"{r.metrics.get('fix_similarity', 0):>7.2%} "
            f"{r.metrics.get('type_accuracy', 0):>8.2%} "
            f"{r.metrics.get('pass_rate', 0):>7.2%}  "
            f"{r.avg_latency_ms:>8.2f}"
        )
    return "\n".join(lines)
