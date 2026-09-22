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
    """Шумный baseline: случайно выбирает тип ошибки и коротко угадывает fix.

    Не читает промпт по существу — работает как «обезьянка с клавиатурой».
    Служит нижней границей: настоящая LLM обязана её обыгрывать.
    """

    name = "noisy-baseline"

    # Список типов ошибок, которые мы вообще ожидаем в T1.
    _KNOWN_TYPES = [
        "SyntaxError", "IndentationError", "NameError", "TypeError",
        "ZeroDivisionError", "E501", "unused-import", "bare-except",
        "mutable-default", "comparison-with-none",
    ]

    # Правдоподобные «шаблоны» фиксов, из которых модель тянет случайно.
    _FIX_TEMPLATES = [
        "if x == 1:",
        "except Exception:",
        "if x is None:",
        "return a / b if b else 0",
        "    return x + 1",
        "",  # пустой fix — тоже валидный вариант (напр. удалить строку)
    ]

    def __init__(self, p_correct: float = 0.5, seed: int = 42) -> None:
        self.p_correct = p_correct
        self._rng = random.Random(seed)

    def complete(self, prompt: str) -> str:
        # С вероятностью p_correct пробуем «угадать» через ORACLE-блок
        # (если он есть в промпте — режим отладки), иначе честно рандомим.
        if self._rng.random() < self.p_correct:
            m = re.search(r"ORACLE_TYPE=(\S+)\s+ORACLE_FIX=(.*?)(?:\n|$)", prompt)
            if m:
                return f"TYPE: {m.group(1)}\nFIX: {m.group(2).strip()}"
        # Честный шум: случайный тип и случайный fix.
        err_type = self._rng.choice(self._KNOWN_TYPES)
        fix = self._rng.choice(self._FIX_TEMPLATES)
        return f"TYPE: {err_type}\nFIX: {fix}"

def parse_t1_output(raw: str) -> dict[str, str]:
    """Достаём из ответа модели тип ошибки и предложенный фикс.

    Убираем обёртку в backticks (```code``` или `code`) — LLM любят её добавлять.
    """
    type_match = _TYPE_LINE_RE.search(raw)
    fix_match = _FIX_LINE_RE.search(raw)

    error_type = type_match.group(1).strip() if type_match else ""
    fix = fix_match.group(1).strip() if fix_match else ""

    # снимаем ``` или ` вокруг фикса
    fix = fix.strip("`").strip()

    return {"error_type": error_type, "fix": fix}
# ---------------------------------------------------------------------------
# GigaChat: облачная модель Сбера. Бесплатный тариф для физлиц.
# Ключ читается из переменной окружения GIGACHAT_CREDENTIALS (см. .env).
# ---------------------------------------------------------------------------

import os


class GigaChatClient(LLMClient):
    """Клиент к GigaChat через официальный SDK."""

    def __init__(self, model: str = "GigaChat-2-Pro") -> None:
        from gigachat import GigaChat  # импорт внутри, чтобы harness работал без SDK
        credentials = os.environ.get("GIGACHAT_CREDENTIALS")
        if not credentials:
            raise RuntimeError(
                "GIGACHAT_CREDENTIALS не задан. "
                "Положи ключ в .env или переменную окружения."
            )
        # verify_ssl_certs=False — временно, для теста. Правильно ставить корневой
        # сертификат Минцифры, но для курсовой этого достаточно.
        self._giga = GigaChat(
            credentials=credentials,
            model=model,
            verify_ssl_certs=False,
        )
        self.name = f"gigachat:{model}"
        self.model_id = model

    def complete(self, prompt: str) -> str:
        response = self._giga.chat(prompt)
        return response.choices[0].message.content