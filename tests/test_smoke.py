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
    """EchoModel — верхняя граница: должна дать 100% на любом кейсе."""
    cases = load_cases(DATASET)
    rows = run(cases, [EchoModel()])
    assert len(rows) == 1
    assert rows[0].metrics["pass_rate"] == 1.0
    assert rows[0].metrics["exact_match"] == 1.0


def test_noisy_model_is_worse_than_oracle() -> None:
    cases = load_cases(DATASET)
    rows = run(cases, [EchoModel(), NoisyModel(p_correct=0.0)])
    by_name = {r.model_name: r for r in rows}
    assert by_name["echo-oracle"].metrics["pass_rate"] > by_name["noisy-baseline"].metrics["pass_rate"]


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