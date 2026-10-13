"""
Task 2 — Security & Logic Bug Detection.

Модель получает фрагмент кода с известной уязвимостью (SQL-инъекция,
race condition, null-deref и т.п.) и должна:

    1. Указать номера строк, содержащих баг.
    2. Классифицировать угрозу по CWE (CWE-89, CWE-416, ...).
    3. Кратко объяснить root cause.

Формат ответа фиксирован — так проще парсить:

    LINES: <номера строк через запятую>
    CWE: <идентификатор, напр. CWE-89>
    CAUSE: <одно предложение>

Строки сниппета в промпте пронумерованы (`3| ...`): модели плохо считают
строки сами, а мы проверяем умение найти баг, а не умение считать.

Метрики (считаются в evaluator.score_t2):
    - Precision / Recall / F1 по номерам строк
    - Accuracy и macro-F1 по CWE-классификации

У одной уязвимости часто несколько корректных CWE (TOCTOU — это и
CWE-367, и родительский CWE-362). Такие альтернативы перечислены в
`metadata.acceptable_cwe` и засчитываются как верный ответ — по аналогии
с `multiple_valid` в T1.
"""

from __future__ import annotations

import re

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You are a security auditor. Given a code snippet, respond strictly as:\n"
    "LINES: <comma-separated 1-based line numbers of the buggy lines>\n"
    "CWE: <single CWE identifier, e.g. CWE-89>\n"
    "CAUSE: <one sentence explaining root cause>\n"
)


def number_lines(snippet: str) -> str:
    """`3| code` — нумерация строк, чтобы модель ссылалась на них без подсчёта."""
    return "\n".join(f"{i}| {line}" for i, line in enumerate(snippet.split("\n"), 1))


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    """Собирает финальный промпт для T2."""
    snippet = case.metadata.get("snippet", "")
    prompt = (
        f"{SYSTEM_PROMPT}\n"
        f"Language: {case.language}\n"
        f"Snippet:\n```\n{number_lines(snippet)}\n```\n"
    )
    if include_oracle:
        # ВНИМАНИЕ: только для baseline-моделей (needs_oracle=True).
        lines = ",".join(str(n) for n in case.expected["lines"])
        prompt += f"\nORACLE_LINES={lines} ORACLE_CWE={case.expected['cwe']}\n"
    return prompt


_LINES_RE = re.compile(r"^\s*\**LINES?\**:\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_CWE_RE = re.compile(r"CWE\s*-?\s*(\d+)", re.IGNORECASE)
_CWE_LINE_RE = re.compile(r"^\s*\**CWE\**:\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_CAUSE_RE = re.compile(r"^\s*\**CAUSE\**:\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)|(\d+)")


def parse_lines(text: str) -> list[int]:
    """'3, 5-7' -> [3, 5, 6, 7]. Диапазоны разворачиваем, мусор игнорируем."""
    found: set[int] = set()
    for m in _RANGE_RE.finditer(text):
        start = int(m.group(1) or m.group(3))
        end = int(m.group(2)) if m.group(2) else start
        if start <= end <= start + 50:  # защита от "1-100000"
            found.update(range(start, end + 1))
    return sorted(found)


def normalize_cwe(text: str) -> str:
    """'cwe 89' / 'CWE-089' -> 'CWE-89'. Пустая строка, если CWE не найден."""
    m = _CWE_RE.search(text)
    return f"CWE-{int(m.group(1))}" if m else ""


def parse_t2_output(raw: str) -> dict:
    """Достаём из ответа модели строки, CWE и объяснение."""
    lines_m = _LINES_RE.search(raw)
    cwe_m = _CWE_LINE_RE.search(raw)
    cause_m = _CAUSE_RE.search(raw)
    return {
        "lines": parse_lines(lines_m.group(1)) if lines_m else [],
        # если строки "CWE:" нет, ищем идентификатор по всему ответу
        "cwe": normalize_cwe(cwe_m.group(1) if cwe_m else raw),
        "cause": cause_m.group(1).strip() if cause_m else "",
    }
