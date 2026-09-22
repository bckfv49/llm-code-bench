"""
Task 2 — Security & Logic Bug Detection.

Модель получает фрагмент кода с известной уязвимостью (SQL-инъекция,
race condition, null-deref и т.п.) и должна:

    1. Указать номера строк, содержащих баг.
    2. Классифицировать угрозу по CWE (CWE-89, CWE-416, ...).
    3. Кратко объяснить root cause.

Метрики:
    - Precision / Recall по номерам строк
    - F1 по CWE-классификации

Пока — заглушка. Полностью будет реализована на этапе 3 роадмапа
(сбор кейсов из GitHub Advisories + база Snyk).
"""

from __future__ import annotations

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You are a security auditor. Given a code snippet, respond strictly as:\n"
    "LINES: <comma-separated 1-based line numbers of the buggy lines>\n"
    "CWE: <single CWE identifier, e.g. CWE-89>\n"
    "CAUSE: <one sentence explaining root cause>\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    raise NotImplementedError("T2 будет реализован после сбора CWE-датасета")
