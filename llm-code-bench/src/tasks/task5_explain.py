"""
Task 5 — Algorithm Explanation.

Оптимизированный, но не документированный кусок кода
(хеш-мап с открытой адресацией, LRU-кэш, аллокатор и т.п.).
Модель должна выдать:

    - что делает алгоритм на человеческом языке
    - оценку временной сложности O(...)
    - оценку по памяти O(...)

Сравниваем ответ с эталонным описанием, написанным senior-инженером.
Оценка через ROUGE-L и/или BERTScore.

Пока — заглушка.
"""

from __future__ import annotations

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You are a senior engineer explaining code. Reply strictly as:\n"
    "SUMMARY: <2-3 sentences of what the code does>\n"
    "TIME: O(<expression>)\n"
    "SPACE: O(<expression>)\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    raise NotImplementedError("T5 требует эталонных описаний от senior-разработчика")
