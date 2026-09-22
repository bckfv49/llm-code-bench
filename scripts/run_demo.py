"""
Демо-прогон бенчмарка.

Без ключей API — только заглушечные модели. Показывает, что стенд
крутится сквозным потоком: JSONL -> harness -> evaluator -> лидерборд.

Запуск из корня репозитория:

    python -m scripts.run_demo
"""

from __future__ import annotations

from pathlib import Path

from src.evaluator import format_leaderboard, run
from src.harness import EchoModel, NoisyModel
from src.tasks.task1_lint import load_cases


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "task1_lint" / "samples.jsonl"


def main() -> None:
    cases = load_cases(DATASET)
    print(f"Загружено кейсов: {len(cases)} (все — T1)\n")

    models = [
        EchoModel(),
        NoisyModel(p_correct=0.5, seed=42),
        NoisyModel(p_correct=0.2, seed=7),
    ]
    # у второй шумной модели поменяем имя, чтобы не путались в лидерборде
    models[2].name = "noisy-baseline-weak"

    rows = run(cases, models)
    print(format_leaderboard(rows))


if __name__ == "__main__":
    main()
