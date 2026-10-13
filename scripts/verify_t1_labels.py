"""
Проверка меток T1 по-настоящему, а не на глаз.

Для каждого кейса error_type сверяется с реальностью:
    SyntaxError / IndentationError / TabError  -> compile() бросает именно это;
    NameError / TypeError / IndexError / ...   -> запуск кода бросает именно это;
    E501                                       -> есть строка длиннее 79 символов;
    правила pylint (unused-import, ...)        -> pylint выдаёт именно это правило.

Код датасета (не модели!) запускается в отдельном процессе с таймаутом.

    python -m scripts.verify_t1_labels data/task1_lint/samples.jsonl
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

SYNTAX = {"SyntaxError", "IndentationError", "TabError"}
RUNTIME = {"NameError", "TypeError", "ZeroDivisionError", "IndexError", "KeyError",
           "AttributeError", "ValueError", "UnboundLocalError"}


def compile_error(src: str) -> str | None:
    try:
        with warnings.catch_warnings():  # SyntaxWarning у ловушек — ожидаемо
            warnings.simplefilter("ignore")
            compile(src, "<case>", "exec")
        return None
    except SyntaxError as exc:
        return type(exc).__name__


def runtime_error(src: str) -> str | None:
    code = f"try:\n    exec({src!r}, {{}})\nexcept Exception as e:\n    print(type(e).__name__)\n"
    out = subprocess.run([sys.executable, "-I", "-W", "ignore", "-c", code],
                         capture_output=True, text=True, timeout=10)
    return out.stdout.strip() or None


def pylint_symbols(src: str) -> set[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src + "\n")
        path = f.name
    try:
        out = subprocess.run([sys.executable, "-m", "pylint", "--output-format=json",
                              "--score=n", path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    return {m["symbol"] for m in json.loads(out.stdout or "[]")}


def verify(error_type: str, snippet: str) -> tuple[bool, str]:
    """(метка подтверждена?, чем проверяли и что получили)."""
    if error_type in SYNTAX:
        got = compile_error(snippet)
        return got == error_type, f"compile() -> {got}"
    if compile_error(snippet):
        return False, f"snippet does not compile: {compile_error(snippet)}"
    if error_type in RUNTIME:
        got = runtime_error(snippet)
        return got == error_type, f"run -> {got}"
    if error_type == "E501":
        longest = max(len(line) for line in snippet.split("\n"))
        return longest > 79, f"longest line {longest}"
    symbols = pylint_symbols(snippet)
    return error_type in symbols, f"pylint -> {sorted(symbols)}"


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/task1_lint/samples.jsonl")
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        ok, why = verify(case["expected"]["error_type"], case["metadata"]["snippet"])
        bad += not ok
        print(f"[{'ok ' if ok else 'BAD'}] {case['case_id']} {case['expected']['error_type']:24s} {why}")
    print(f"{'[OK]' if not bad else '[FAIL]'} {path}: {bad} unverified label(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
