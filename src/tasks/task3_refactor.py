"""
Task 3 — Refactoring & Modernization.

Модель получает функцию в устаревшем стиле (цикл с append вместо list
comprehension, `%`-форматирование, ручной подсчёт вместо Counter и т.п.)
и переписывает её по современным best practices.

Проверка по заданию — unit-тестами:
    1. Код модели + тесты кейса запускаются в Docker-песочнице
       (src/sandbox.py). Тесты должны пройти — функциональность сохранена.
    2. Сложность должна снизиться: ни количество строк, ни синтаксическая
       сложность не выросли, и хотя бы одно из них стало меньше.

Обе меры сложности считаются по AST, а не по тексту:
    loc        — число логических строк в ast.unparse(кода): не зависит от
                 комментариев, пустых строк и переносов длинных выражений;
    ast_nodes  — число узлов синтаксического дерева (синтаксическая сложность).
Докстринги из подсчёта исключаются: документация не делает код сложнее,
и модель не должна проигрывать за то, что её добавила.
"""

from __future__ import annotations

import ast
import re

from ..schema import BenchCase


SYSTEM_PROMPT = (
    "You are a refactoring expert. Rewrite the given function according to\n"
    "modern best practices for the target language. Preserve behaviour.\n"
    "Reply with a single code block and nothing else.\n"
)


def build_prompt(case: BenchCase, include_oracle: bool = False) -> str:
    """Собирает финальный промпт для T3."""
    entry = case.metadata["entry_point"]
    prompt = (
        f"{SYSTEM_PROMPT}"
        f"Keep the function name `{entry}` and its signature. "
        f"You may add imports from the standard library.\n\n"
        f"Language: {case.language}\n"
        f"Code:\n```python\n{case.metadata['snippet']}\n```\n"
    )
    if include_oracle:
        # ВНИМАНИЕ: только для baseline-моделей (needs_oracle=True).
        prompt += f"\nORACLE_T3_BEGIN\n{case.expected['reference_solution']}\nORACLE_T3_END\n"
    return prompt


_CODE_BLOCK_RE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(raw: str) -> str:
    """Код из ответа модели: первый ```-блок, а если блока нет — весь ответ."""
    m = _CODE_BLOCK_RE.search(raw)
    return (m.group(1) if m else raw).strip()


def _strip_docstrings(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]


def code_metrics(src: str) -> dict[str, int] | None:
    """{'loc', 'ast_nodes'} для кода, None — если код не парсится."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    _strip_docstrings(tree)
    loc = sum(1 for line in ast.unparse(tree).splitlines() if line.strip())
    return {"loc": loc, "ast_nodes": sum(1 for _ in ast.walk(tree))}


def is_simpler(before: dict[str, int], after: dict[str, int]) -> bool:
    """Правило задания: ничего не выросло и хотя бы одна мера снизилась."""
    not_worse = all(after[k] <= before[k] for k in before)
    better = any(after[k] < before[k] for k in before)
    return not_worse and better


def build_test_script(code: str, tests: str, nonce: str) -> str:
    """Код модели + тесты кейса + метка успеха.

    Метка `nonce` генерируется заново на каждый запуск и печатается только
    после всех assert'ов. Так код модели не может «пройти» тесты, завершив
    процесс раньше (например, через sys.exit(0)) — метки в выводе не будет.
    """
    return f"{code}\n\n\n{tests}\n\nprint({nonce!r})\n"
