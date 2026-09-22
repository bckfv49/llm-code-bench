"""
Evaluator — ядро оценки.

Принимает список кейсов, список моделей (LLMClient), прогоняет
каждый кейс через каждую модель, вычисляет метрики и агрегирует
их в лидерборд.

Пока реализован только T1. Каждый следующий таск добавляет свою
функцию scorer'а с сигнатурой `(case, prediction) -> CaseResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from .harness import LLMClient, parse_t1_output
from .schema import BenchCase, CaseResult, Prediction
from .tasks.task1_lint import build_prompt


Scorer = Callable[[BenchCase, Prediction], CaseResult]


def score_t1(case: BenchCase, pred: Prediction) -> CaseResult:
    """Метрики Task 1: Exact Match фикса + точность классификации типа."""
    parsed = parse_t1_output(pred.raw_output)
    pred.parsed = parsed

    type_correct = parsed["error_type"] == case.expected["error_type"]
    fix_correct = parsed["fix"].strip() == case.expected["fix"].strip()

    return CaseResult(
        case_id=case.case_id,
        model_name=pred.model_name,
        task=case.task,
        metrics={
            "exact_match": float(fix_correct),
            "type_accuracy": float(type_correct),
        },
        passed=type_correct and fix_correct,
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
            prompt = build_prompt(case, include_oracle=True)  # demo-режим
            pred = model.predict(case.case_id, prompt)
            scorer = SCORERS.get(case.task)
            if scorer is None:
                continue
            result = scorer(case, pred)
            per_task.setdefault(case.task, []).append(result)
            latencies.setdefault(case.task, []).append(pred.latency_ms)

        for task, results in per_task.items():
            agg: dict[str, float] = {}
            keys = results[0].metrics.keys()
            for k in keys:
                agg[k] = mean(r.metrics[k] for r in results)
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
        f"{'model':<20} {'task':<5} {'n':>4}  {'EM':>7} {'TypeAcc':>8} "
        f"{'Pass':>7}  {'lat(ms)':>8}"
    ]
    lines.append("-" * len(lines[0]))
    for r in sorted(rows, key=lambda x: -x.metrics.get("pass_rate", 0)):
        lines.append(
            f"{r.model_name:<20} {r.task:<5} {r.n_cases:>4}  "
            f"{r.metrics.get('exact_match', 0):>7.2%} "
            f"{r.metrics.get('type_accuracy', 0):>8.2%} "
            f"{r.metrics.get('pass_rate', 0):>7.2%}  "
            f"{r.avg_latency_ms:>8.2f}"
        )
    return "\n".join(lines)
