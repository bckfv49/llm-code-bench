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