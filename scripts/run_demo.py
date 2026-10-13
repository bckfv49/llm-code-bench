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

import os

from src.evaluator import format_leaderboard, run
from src.harness import LLMClient, NoisyModel, GigaChatClient, OpenAIClient
from src.tasks.task1_lint import load_cases


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "task1_lint" / "samples.jsonl"
RESULTS = ROOT / "results"


def build_models() -> list[LLMClient]:
    """Baseline'ы всегда, реальные модели — те, для которых есть ключ в .env.

    Добавить модель = дописать переменные в .env, код править не нужно:
        GIGACHAT_CREDENTIALS=...            -> GigaChat
        OPENAI_API_KEY=... OPENAI_MODEL=... -> OpenAI
        LOCAL_LLM_BASE_URL=http://localhost:11434/v1 LOCAL_LLM_MODEL=...
                                            -> Ollama / llama.cpp / vLLM / LM Studio
    """
    weak = NoisyModel(p_correct=0.2, seed=7)
    weak.name = "noisy-baseline-weak"
    models: list[LLMClient] = [NoisyModel(p_correct=0.5, seed=42), weak]

    if os.environ.get("GIGACHAT_CREDENTIALS"):
        models.append(GigaChatClient(os.environ.get("GIGACHAT_MODEL", "GigaChat-2-Pro")))
    if os.environ.get("OPENAI_API_KEY"):
        models.append(OpenAIClient(os.environ.get("OPENAI_MODEL", "gpt-4o-mini")))
    if base_url := os.environ.get("LOCAL_LLM_BASE_URL"):
        model = os.environ.get("LOCAL_LLM_MODEL", "local")
        models.append(OpenAIClient(model, base_url=base_url, name=f"local:{model}"))

    return models


def main() -> None:
    cases = load_cases(DATASET)
    print(f"Загружено кейсов: {len(cases)} (все - T1)\n")

    models = build_models()
    print("Модели: " + ", ".join(m.name for m in models) + "\n")

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