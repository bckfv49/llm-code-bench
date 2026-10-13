"""
Smoke-тесты: проверяют, что пайплайн собирается и крутится
на dummy-моделях. Запуск: `python -m pytest tests/` из корня.
"""

from __future__ import annotations

from pathlib import Path

from src.evaluator import format_leaderboard, run
from src.harness import EchoModel, NoisyModel, parse_t1_output
from src.tasks.task1_lint import load_cases


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "task1_lint" / "samples.jsonl"


def test_dataset_loads() -> None:
    cases = load_cases(DATASET)
    assert len(cases) >= 5
    for c in cases:
        assert c.task == "T1"
        assert c.expected["error_type"]


def test_echo_model_is_perfect() -> None:
    """EchoModel — sanity-check парсера. Работает только с oracle-блоком в промпте."""
    from src.tasks.task1_lint import build_prompt
    cases = load_cases(DATASET)
    model = EchoModel()
    for case in cases:
        raw = model.complete(build_prompt(case, include_oracle=True))
        parsed = parse_t1_output(raw)
        assert parsed["error_type"] == case.expected["error_type"]
        assert parsed["fix"].strip() == case.expected["fix"].strip()


def test_noisy_model_is_worse_than_oracle() -> None:
    """NoisyModel с p_correct=0.0 должна давать 0 совпадений на oracle-промпте,
    EchoModel — 100%. Значит метрика реально что-то меряет."""
    from src.tasks.task1_lint import build_prompt
    cases = load_cases(DATASET)
    echo = EchoModel()
    noisy = NoisyModel(p_correct=0.0, seed=42)

    echo_hits = 0
    noisy_hits = 0
    for case in cases:
        prompt = build_prompt(case, include_oracle=True)
        e = parse_t1_output(echo.complete(prompt))
        n = parse_t1_output(noisy.complete(prompt))
        if e["error_type"] == case.expected["error_type"] and e["fix"].strip() == case.expected["fix"].strip():
            echo_hits += 1
        if n["error_type"] == case.expected["error_type"] and n["fix"].strip() == case.expected["fix"].strip():
            noisy_hits += 1

    assert echo_hits == len(cases)   # 100% на oracle
    assert noisy_hits < echo_hits    # noisy строго хуже

def test_output_parser() -> None:
    raw = "TYPE: SyntaxError\nFIX: if x == 1:"
    parsed = parse_t1_output(raw)
    assert parsed["error_type"] == "SyntaxError"
    assert parsed["fix"] == "if x == 1:"


def test_leaderboard_format() -> None:
    cases = load_cases(DATASET)
    rows = run(cases, [EchoModel()])
    text = format_leaderboard(rows)
    assert "echo-oracle" in text
    assert "T1" in text



def test_dataset_ids_are_unique() -> None:
    """case_id должен быть уникален в пределах датасета."""
    cases = load_cases(DATASET)
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))


def test_validator_accepts_current_dataset() -> None:
    """Валидатор должен принимать актуальный T1-датасет без ошибок."""
    from scripts.validate_dataset import validate

    assert validate(DATASET) == []

# --- мягкие метрики -------------------------------------------------------


def test_soft_metrics_forgive_cosmetics() -> None:
    """AST-сравнение должно прощать пробелы и кавычки, Exact Match — нет."""
    from src.evaluator import soft_metrics

    m = soft_metrics("if x==1 :", "if x == 1:")
    assert m["ast_match"] == 1.0
    assert m["fix_similarity"] > 0.8

    m = soft_metrics('s = "a"', "s = 'a'")
    assert m["ast_match"] == 1.0


def test_soft_metrics_still_catch_wrong_fix() -> None:
    from src.evaluator import soft_metrics

    m = soft_metrics("except ValueError:", "if x is None:")
    assert m["ast_match"] == 0.0
    assert m["fix_similarity"] < 0.5


def test_soft_metrics_skip_ast_on_garbage() -> None:
    """Непарсящийся ответ не должен ломать прогон — ast_match просто не считается."""
    from src.evaluator import soft_metrics

    m = soft_metrics("!!! not python @@@", "if x == 1:")
    assert "ast_match" not in m
    assert 0.0 <= m["fix_similarity"] <= 1.0


# --- мутационная генерация ------------------------------------------------


def test_mutants_are_verified_and_labelled() -> None:
    """Каждый мутант должен ломаться ровно так, как обещает его метка."""
    from scripts.mutate_t1 import MUTATORS, _compile_error, generate

    expected_error = {m[0]: m[3] for m in MUTATORS}
    cases = generate(check=True)
    assert len(cases) >= 5
    for c in cases:
        assert _compile_error(c["metadata"]["snippet"]) == expected_error[c["expected"]["error_type"]]
        assert c["expected"]["fix"]  # fix = исходная строка, пустой невозможен


def test_mutant_touches_exactly_one_line_and_fix_restores_donor() -> None:
    """Мутация должна менять ровно одну строку, а эталонный fix — возвращать
    донора байт в байт. Иначе fix «исправляет» не то, что сломано."""
    from scripts.mutate_t1 import CLEAN_SNIPPETS, mutate

    for donor in CLEAN_SNIPPETS:
        donor_lines = donor.split("\n")
        for _error_type, mutant, fix in mutate(donor):
            mutant_lines = mutant.split("\n")
            assert len(mutant_lines) == len(donor_lines)
            diff = [i for i, (a, b) in enumerate(zip(donor_lines, mutant_lines)) if a != b]
            assert len(diff) == 1, f"мутация задела {len(diff)} строк"
            restored = mutant_lines[: diff[0]] + [fix] + mutant_lines[diff[0] + 1 :]
            assert "\n".join(restored) == donor


# --- сбор из git ----------------------------------------------------------


def test_git_miner_picks_single_line_hunks() -> None:
    """Однострочный ханк берём, многострочный — нет (он не влезает в формат T1)."""
    from scripts.mine_git_fixes import iter_single_line_fixes

    diff = (
        "\x00abc123\x00fix: typo\n"
        "+++ b/app.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def f(x):\n"
        "-    if x = 1:\n"
        "+    if x == 1:\n"
        "         return 1\n"
        "@@ -10,4 +10,5 @@\n"
        "-    a = 1\n"
        "-    b = 2\n"
        "+    a, b = 1, 2\n"
    )
    found = list(iter_single_line_fixes(diff, [".py"]))
    assert len(found) == 1
    sha, msg, path, before, after, _ctx = found[0]
    assert (sha, path) == ("abc123", "app.py")
    assert after.strip() == "if x == 1:"


def test_git_miner_respects_extensions() -> None:
    from scripts.mine_git_fixes import iter_single_line_fixes

    diff = (
        "\x00abc123\x00fix: typo\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    assert list(iter_single_line_fixes(diff, [".py"])) == []


# --- сборка списка моделей ------------------------------------------------


def test_build_models_is_env_driven(monkeypatch) -> None:
    """Без ключей — только baseline'ы. С LOCAL_LLM_BASE_URL — плюс локальная."""
    from scripts.run_demo import build_models

    for var in ("GIGACHAT_CREDENTIALS", "OPENAI_API_KEY", "LOCAL_LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert [m.name for m in build_models()] == ["noisy-baseline", "noisy-baseline-weak"]

    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5-coder")
    assert "local:qwen2.5-coder" in [m.name for m in build_models()]


# --- T2: поиск уязвимостей ------------------------------------------------

T2_DATASET = ROOT / "data" / "task2_security" / "samples.jsonl"


def test_t2_dataset_valid_and_covers_domains() -> None:
    """T2 проходит валидатор и покрывает все три домена из задания."""
    from scripts.validate_dataset import validate

    assert validate(T2_DATASET) == []
    cases = load_cases(T2_DATASET)
    assert len(cases) >= 20
    assert {c.metadata["domain"] for c in cases} == {"web", "ml", "system"}


def test_t2_validator_rejects_bad_line(tmp_path) -> None:
    """Номер строки за пределами сниппета — ошибка разметки."""
    import json

    from scripts.validate_dataset import validate

    bad = {
        "case_id": "T2-bad", "task": "T2", "language": "python", "prompt": "",
        "expected": {"lines": [9], "cwe": "CWE-89", "cause": "x"},
        "metadata": {"snippet": "a = 1\nb = 2"},
    }
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    assert any("out of range" in e for e in validate(path))


def test_t2_parser_handles_ranges_and_messy_cwe() -> None:
    from src.tasks.task2_security import parse_t2_output

    parsed = parse_t2_output("**LINES:** 3, 5-7\n**CWE:** cwe 089\nCAUSE: injection")
    assert parsed["lines"] == [3, 5, 6, 7]
    assert parsed["cwe"] == "CWE-89"
    assert parsed["cause"] == "injection"


def test_t2_prompt_numbers_lines_and_hides_oracle() -> None:
    from src.tasks.task2_security import build_prompt

    case = load_cases(T2_DATASET)[0]
    clean = build_prompt(case, include_oracle=False)
    assert "1| def get_user" in clean
    assert "ORACLE" not in clean
    assert "ORACLE_CWE=CWE-89" in build_prompt(case, include_oracle=True)


def test_t2_scorer_precision_recall_and_acceptable_cwe() -> None:
    """Лишняя строка бьёт по precision, альтернативный CWE засчитывается."""
    from src.evaluator import score_t2
    from src.schema import BenchCase, Prediction

    case = BenchCase(
        case_id="T2-x", task="T2", language="python", prompt="",
        expected={"lines": [2, 3], "cwe": "CWE-367", "cause": ""},
        metadata={"snippet": "a\nb\nc\nd", "acceptable_cwe": ["CWE-362"]},
    )
    pred = Prediction(case_id="T2-x", model_name="m", raw_output="LINES: 2, 4\nCWE: CWE-362")
    r = score_t2(case, pred)
    assert r.metrics["line_precision"] == 0.5
    assert r.metrics["line_recall"] == 0.5
    assert r.metrics["cwe_accuracy"] == 1.0
    assert r.labels == {"gold": "CWE-367", "pred": "CWE-367"}
    assert not r.passed  # одна из двух строк с багом не найдена


def test_macro_f1() -> None:
    from src.evaluator import macro_f1

    assert macro_f1([("A", "A"), ("B", "B")]) == 1.0
    # A: tp=1 fn=1 -> 2/3; B: tp=0 fp=1 -> 0  => (2/3 + 0) / 2
    assert abs(macro_f1([("A", "A"), ("A", "B")]) - 1 / 3) < 1e-9


def test_t2_echo_perfect_and_noisy_ladder() -> None:
    from src.harness import EchoModel, NoisyModel

    cases = load_cases(T2_DATASET)
    rows = {r.model_name: r for r in run(cases, [
        EchoModel(), NoisyModel(p_correct=0.0, seed=1),
    ])}
    assert rows["echo-oracle"].metrics["pass_rate"] == 1.0
    assert rows["echo-oracle"].metrics["cwe_macro_f1"] == 1.0
    assert rows["noisy-baseline"].metrics["pass_rate"] < 1.0


def test_leaderboard_has_block_per_task() -> None:
    from src.harness import EchoModel

    cases = load_cases(DATASET) + load_cases(T2_DATASET)
    text = format_leaderboard(run(cases, [EchoModel()]))
    assert "TypeAcc" in text and "CWE-F1" in text
