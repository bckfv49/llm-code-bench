"""
Harness — единый интерфейс к LLM.

Идея простая: все реальные бэкенды (OpenAI, GigaChat, Anthropic, локальный
vLLM) реализуют один и тот же класс `LLMClient`. Evaluator ничего не знает
о том, что стоит внутри — он просто вызывает `.complete(prompt)`.

Пока в реализации только две заглушки: `EchoModel` и `NoisyModel`. Они
нужны, чтобы весь стенд крутился end-to-end без ключей API. Реальные
клиенты появятся отдельными классами в этом же файле.
"""

from __future__ import annotations

import random
import re
import time
from abc import ABC, abstractmethod

from .schema import Prediction


class LLMClient(ABC):
    """Абстрактный клиент к языковой модели."""

    name: str

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Возвращает сырой текстовый ответ модели."""

    def predict(self, case_id: str, prompt: str) -> Prediction:
        """Обёртка с измерением времени и обработкой исключений."""
        started = time.perf_counter()
        try:
            raw = self.complete(prompt)
            err: str | None = None
        except Exception as exc:  # noqa: BLE001 — ловим всё, чтобы прогон не падал
            raw = ""
            err = f"{type(exc).__name__}: {exc}"
        latency_ms = (time.perf_counter() - started) * 1000
        return Prediction(
            case_id=case_id,
            model_name=self.name,
            raw_output=raw,
            latency_ms=latency_ms,
            tokens_in=len(prompt.split()),
            tokens_out=len(raw.split()),
            error=err,
        )


# ---------------------------------------------------------------------------
# Заглушечные модели для локального прогона без внешних API.
# ---------------------------------------------------------------------------

_FIX_LINE_RE = re.compile(r"^FIX:\s*(.+)$", re.MULTILINE)
_TYPE_LINE_RE = re.compile(r"^TYPE:\s*(\S+)", re.MULTILINE)


class EchoModel(LLMClient):
    """Отвечает эталоном, зашитым прямо в промпт. Верхняя граница точности."""

    name = "echo-oracle"

    def complete(self, prompt: str) -> str:
        # Промпт для T1 содержит блок ORACLE в конце — только для теста.
        m = re.search(r"ORACLE_TYPE=(\S+)\s+ORACLE_FIX=(.*?)(?:\n|$)", prompt)
        if not m:
            return "TYPE: unknown\nFIX: "
        return f"TYPE: {m.group(1)}\nFIX: {m.group(2).strip()}"


class NoisyModel(LLMClient):
    """С вероятностью p возвращает правильный ответ, иначе — правдоподобный мусор."""

    name = "noisy-baseline"

    def __init__(self, p_correct: float = 0.5, seed: int = 42) -> None:
        self.p_correct = p_correct
        self._rng = random.Random(seed)

    def complete(self, prompt: str) -> str:
        m = re.search(r"ORACLE_TYPE=(\S+)\s+ORACLE_FIX=(.*?)(?:\n|$)", prompt)
        if not m:
            return "TYPE: unknown\nFIX: "
        if self._rng.random() < self.p_correct:
            return f"TYPE: {m.group(1)}\nFIX: {m.group(2).strip()}"
        # неверный тип и слегка испорченный фикс
        return f"TYPE: SyntaxError\nFIX: {m.group(2).strip()[:-1]}"


def parse_t1_output(raw: str) -> dict[str, str]:
    """Достаём из ответа модели тип ошибки и предложенный фикс."""
    type_match = _TYPE_LINE_RE.search(raw)
    fix_match = _FIX_LINE_RE.search(raw)
    return {
        "error_type": type_match.group(1).strip() if type_match else "",
        "fix": fix_match.group(1).strip() if fix_match else "",
    }
