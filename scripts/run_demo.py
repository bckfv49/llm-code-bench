"""
Демо-прогон бенчмарка.

Прогоняет все кейсы через все модели, печатает лидерборд в консоль
и сохраняет результаты в папку results/ (leaderboard.txt + run.json),

Запуск из корня репозитория -    python -m scripts.run_demo
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # подтягиваем .env в переменные окружения

from src.evaluator import format_leaderboard, run
from src.harness import NoisyModel, GigaChatClient
from src.tasks.task1_lint import load_cases


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "task1_lint" / "samples.jsonl"
RESULTS = ROOT / "results"


def main() -> None:
    cases = load_cases(DATASET)
    print(f"Загружено кейсов: {len(cases)} (все — T1)\n")

    models = [
        GigaChatClient(),
        NoisyModel(p_correct=0.5, seed=42),
        NoisyModel(p_correct=0.2, seed=7),
    ]
    models[2].name = "noisy-baseline-weak"

    rows = run(cases, models)
    table = format_leaderboard(rows)
    print(table)

    # Сохраняем результаты в файлы, чтобы показывать без повторного запуска.
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "leaderboard.txt").write_text(table, encoding="utf-8")

    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "n_cases": len(cases),
        "rows": [asdict(r) for r in rows],
    }
    (RESULTS / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nРезультаты сохранены в {RESULTS.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()