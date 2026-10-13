"""
Мутационный генератор кейсов T1.

Идея мутационного тестирования наоборот: обычно мутанты проверяют тесты,
здесь они проверяют модель. Берём заведомо чистый сниппет, вносим ровно
одну поломку известного типа — и получаем кейс, у которого эталон известен
по построению: error_type = тип мутации, fix = исходная строка.

Плюс к ручному датасету: кейсы дешёвые и их можно нагенерить сколько нужно,
а `--check` гарантирует, что мутант действительно сломан (для синтаксических
мутаций это проверяется реальным `compile()`).

    python -m scripts.mutate_t1                                  # в stdout
    python -m scripts.mutate_t1 -o data/task1_lint/mutants.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Чистые сниппеты-донóры. Каждый компилируется без ошибок.
CLEAN_SNIPPETS = [
    "def inc(x):\n    return x + 1",
    "if count == 0:\n    print('empty')",
    "def safe_div(a, b):\n    if b == 0:\n        return 0\n    return a / b",
    "def load(path, cache=None):\n    if cache is None:\n        cache = {}\n    return cache",
    "def read(path):\n    try:\n        return open(path).read()\n    except OSError:\n        return ''",
    "def total(items):\n    result = 0\n    for it in items:\n        result += it\n    return result",
    "def name_of(user):\n    if user is None:\n        return 'anon'\n    return user.name",
]

# Мутатор = (error_type, что ищем, чем заменяем, ожидаемое исключение compile()).
# Последнее поле = None для lint-мутаций: код остаётся валидным, ломается стиль.
MUTATORS: list[tuple[str, str, str, str | None]] = [
    # `==` -> `=` в условии: классический SyntaxError.
    ("SyntaxError", r"^(\s*if .+?) == (.+):$", r"\1 = \2:", "SyntaxError"),
    # Срезаем отступ у тела функции. Работает только когда дедент реально даёт
    # IndentationError: у последней строки функции получается "return outside
    # function", то есть другой тип ошибки — такой мутант отбрасывает --check.
    ("IndentationError", r"^    (return .+)$", r"\1", "IndentationError"),
    # Конкретный except -> голый.
    ("bare-except", r"^(\s*)except OSError:$", r"\1except:", None),
    # `is None` -> `== None` (pylint singleton-comparison, pycodestyle E711).
    ("singleton-comparison", r"^(\s*if \w+) is None:$", r"\1 == None:", None),
    # None-дефолт -> мутабельный (pylint dangerous-default-value).
    ("dangerous-default-value", r"^(def \w+\(.*?)cache=None(.*)$", r"\1cache={}\2", None),
]


def mutate(snippet: str) -> list[tuple[str, str, str]]:
    """Все возможные одиночные мутации сниппета: (error_type, мутант, fix)."""
    out: list[tuple[str, str, str]] = []
    lines = snippet.split("\n")
    for error_type, pattern, repl, _expected in MUTATORS:
        rx = re.compile(pattern)
        for i, line in enumerate(lines):
            mutated_line, n = rx.subn(repl, line)
            if not n:
                continue
            mutant = "\n".join(lines[:i] + [mutated_line] + lines[i + 1 :])
            out.append((error_type, mutant, line))  # fix = исходная строка
    return out


def _compile_error(src: str) -> str | None:
    """Имя класса исключения от compile(), либо None если код валиден."""
    try:
        compile(src, "<mutant>", "exec")
        return None
    except SyntaxError as exc:
        return type(exc).__name__


def generate(check: bool = True) -> list[dict]:
    """Собирает кейсы по всем донорам. check=True отбрасывает мутанты, которые
    сломались не так, как обещал мутатор — иначе в датасет уедет неверная метка."""
    expected_error = {m[0]: m[3] for m in MUTATORS}
    cases: list[dict] = []
    for snippet in CLEAN_SNIPPETS:
        assert _compile_error(snippet) is None, f"донор не компилируется:\n{snippet}"
        for error_type, mutant, fix in mutate(snippet):
            actual = _compile_error(mutant)
            if check and actual != expected_error[error_type]:
                print(
                    f"[skip] {error_type}: compile() дал {actual}, "
                    f"ожидался {expected_error[error_type]}",
                    file=sys.stderr,
                )
                continue
            cases.append(
                {
                    "case_id": f"T1-mut-{len(cases) + 1:04d}",
                    "task": "T1",
                    "language": "python",
                    "prompt": "",
                    "expected": {"error_type": error_type, "fix": fix.strip()},
                    "metadata": {
                        "snippet": mutant,
                        "source": "mutation",
                        "mutation_verified": check,
                    },
                }
            )
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", type=Path, help="куда писать JSONL (по умолчанию stdout)")
    ap.add_argument("--no-check", action="store_true", help="не проверять мутанты compile()")
    args = ap.parse_args()

    cases = generate(check=not args.no_check)
    text = "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"[OK] {len(cases)} кейсов -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
