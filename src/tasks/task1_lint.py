"""
Task 1 — Static Analysis Prediction.

Модели дают фрагмент кода с ошибкой (SyntaxError / Pylint warning).
Она должна назвать тип ошибки и предложить исправленную строку.

Формат ответа модели фиксирован — так проще парсить:

    TYPE: <идентификатор ошибки из списка ERROR_TYPES>
    FIX: <исправленная строка | DELETE>

Тип выбирается из закрытого списка ERROR_TYPES, который есть в промпте:
это классификация с выбором из известных классов, а не угадывание
названия. Метки — настоящие имена: исключения Python (проверены
compile()/запуском), правила pylint (проверены pylint) и код pycodestyle
E501. В список намеренно добавлены классы, которых нет в датасете, чтобы
ответ нельзя было угадать перебором.

Если строку нужно удалить (например, неиспользуемый импорт), модель
отвечает `FIX: DELETE`; в эталоне это пустая строка.

Для демо мы дописываем в конец промпта служебный блок ORACLE_*, который
читают заглушечные модели (`EchoModel`, `NoisyModel`). В боевом режиме
этот блок убирается — реальные LLM его никогда не увидят.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import BenchCase


# Допустимые типы ошибок. Порядок не несёт смысла; KeyError, ValueError,
# UnboundLocalError, unused-variable и redefined-builtin в датасете не
# встречаются — это дистракторы.
ERROR_TYPES = (
    # исключения Python
    "SyntaxError", "IndentationError", "TabError", "NameError", "TypeError",
    "ZeroDivisionError", "IndexError", "KeyError", "AttributeError",
    "ValueError", "UnboundLocalError",
    # правила pylint
    "unused-import", "unused-variable", "bare-except", "dangerous-default-value",
    "singleton-comparison", "literal-comparison", "assert-on-tuple",
    "implicit-str-concat", "no-method-argument", "redefined-builtin",
    # pycodestyle
    "E501",
)

SYSTEM_PROMPT = (
    "You are a senior code reviewer. Given a code snippet with a static\n"
    "analysis issue, answer strictly in the following format and nothing else:\n"
    "TYPE: <one identifier from the allowed list below; pick the most specific>\n"
    "FIX: <the single corrected line of code; if the line must be removed, write DELETE>\n"
    "Allowed TYPE values: " + ", ".join(ERROR_TYPES) + "\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    """Собирает финальный промпт для T1."""
    lang = case.language
    snippet = case.metadata.get("snippet", "")
    prompt = (
        f"{SYSTEM_PROMPT}\n"
        f"Language: {lang}\n"
        f"Snippet:\n```\n{snippet}\n```\n"
    )
    if include_oracle:
        # ВНИМАНИЕ: только для demo-моделей. Настоящие LLM это НЕ получают.
        prompt += (
            f"\nORACLE_TYPE={case.expected['error_type']} "
            f"ORACLE_FIX={case.expected['fix']}\n"
        )
    return prompt


def load_cases(path: str | Path) -> list[BenchCase]:
    """Читает JSONL с кейсами T1."""
    cases: list[BenchCase] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(BenchCase(**json.loads(line)))
    return cases
