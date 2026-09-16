"""
Общая схема данных бенчмарка.

Каждый кейс в датасете хранится как одна строка JSONL со следующими полями.
Отдельные модули задач (T1..T5) кладут свои специфичные поля в `expected`
и `metadata` — схема остаётся единой.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskId = Literal["T1", "T2", "T3", "T4", "T5"]


class BenchCase(BaseModel):
    """Один тестовый кейс бенчмарка."""

    case_id: str = Field(..., description="Уникальный ID, напр. T1-py-0001")
    task: TaskId = Field(..., description="К какому таску относится кейс")
    language: str = Field(..., description="python | java | cpp | csharp | ...")
    prompt: str = Field(..., description="Готовый текст для отправки в LLM")
    expected: dict[str, Any] = Field(
        ...,
        description="Эталон — форма зависит от таска (см. tasks/*.py)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Источник, CWE, ссылка на коммит и т.п.",
    )


class Prediction(BaseModel):
    """Ответ модели на один кейс + служебные метрики прогона."""

    case_id: str
    model_name: str
    raw_output: str = Field(..., description="Сырой текст ответа модели")
    parsed: dict[str, Any] = Field(
        default_factory=dict,
        description="Распарсенный ответ (специфично для таска)",
    )
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None


class CaseResult(BaseModel):
    """Результат сравнения одного предсказания с эталоном."""

    case_id: str
    model_name: str
    task: TaskId
    metrics: dict[str, float] = Field(default_factory=dict)
    passed: bool = False
