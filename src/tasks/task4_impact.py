"""
Task 4 — Impact Analysis.

Вход: срез монорепо + вопрос вида
"Что сломается, если поменять сигнатуру функции calculate_tax()
в модуле A?". Модель должна перечислить файлы / модули,
которые придётся править.

Эталонный граф вызовов строится через tree-sitter или Language
Server Protocol на этапе сбора датасета.

Метрика: Recall покрытия — доля реально задетых файлов,
которые модель нашла.

Пока — заглушка.
"""

from __future__ import annotations

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You will be given a subset of a repository and a change description.\n"
    "List every file (relative path, one per line) that will need editing\n"
    "to keep the codebase compiling. Answer as:\n"
    "FILES:\n"
    "  <path/one>\n"
    "  <path/two>\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    raise NotImplementedError("T4 требует граф вызовов через tree-sitter")
