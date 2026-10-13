"""
Демо-прогон бенчмарка.

Прогоняет все кейсы через все модели, печатает лидерборд в консоль
и сохраняет результаты в папку results/ (leaderboard.txt + run.json),

Запуск из корня репозитория -    python -m scripts.run_demo
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # подтягиваем .env в переменные окружения

import os

from src.evaluator import format_leaderboard, run
from src.sandbox import docker_available
from src.harness import LLMClient, NoisyModel, GigaChatClient, OpenAIClient
from src.tasks.task1_lint import load_cases


ROOT = Path(__file__).resolve().parent.parent
DATASETS = [
    ROOT / "data" / "task1_lint" / "samples.jsonl",
    ROOT / "data" / "task2_security" / "samples.jsonl",
]
# T3 запускает код модели — по заданию только в Docker-песочнице.
T3_DATASET = ROOT / "data" / "task3_refactor" / "samples.jsonl"
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
    cases = [c for path in DATASETS for c in load_cases(path)]
    docker_ok, why = docker_available()
    if docker_ok:
        cases += load_cases(T3_DATASET)
    else:
        print(f"T3 пропущен: {why}. Код модели запускается только в Docker.\n")
    by_task = Counter(c.task for c in cases)
    print(f"Загружено кейсов: {len(cases)} ("
          + ", ".join(f"{t}: {n}" for t, n in sorted(by_task.items())) + ")\n")

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