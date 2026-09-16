"""
Task 3 — Refactoring & Modernization.

Модель получает функцию в устаревшем стиле и переписывает её
по современным best practices. Проверка — unit-тестами: если
все тесты проходят И количество строк / цикломатическая сложность
снизились, кейс засчитывается.

Прогон тестов идёт в Docker-песочнице (см. TODO в roadmap).

Пока — заглушка.
"""

from __future__ import annotations

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You are a refactoring expert. Rewrite the given function according to\n"
    "modern best practices for the target language. Preserve behaviour.\n"
    "Reply with a single code block and nothing else.\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    raise NotImplementedError("T3 требует Docker-песочницу — см. roadmap")
