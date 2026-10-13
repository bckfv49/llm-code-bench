"""
валидатор JSONL-датасета.

Проверяет, что каждый кейс парсится в BenchCase, что case_id уникальны
и что expected непустой

Запуск -    python -m scripts.validate_dataset data/task1_lint/samples.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from src.schema import BenchCase


def validate(path: Path) -> list[str]:
    """Возвращает список ошибок (пустой = всё ок)."""
    errors: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                case = BenchCase(**json.loads(line))
            except (json.JSONDecodeError, ValidationError) as exc:
                errors.append(f"line {i}: {exc}")
                continue
            if case.case_id in seen:
                errors.append(f"line {i}: duplicate case_id {case.case_id!r}")
            seen.add(case.case_id)
            if not case.expected:
                errors.append(f"line {i}: expected is empty")
            if case.task == "T2":
                errors.extend(f"line {i}: {e}" for e in _check_t2(case))
    return errors


def _check_t2(case: BenchCase) -> list[str]:
    """T2: номера строк существуют в сниппете, CWE в формате CWE-<число>."""
    errs: list[str] = []
    n = len(case.metadata.get("snippet", "").split("\n"))
    lines = case.expected.get("lines")
    if not lines or not all(isinstance(x, int) and 1 <= x <= n for x in lines):
        errs.append(f"expected.lines {lines!r} out of range 1..{n}")
    for cwe in [case.expected.get("cwe", ""), *case.metadata.get("acceptable_cwe", [])]:
        if not re.fullmatch(r"CWE-\d+", cwe):
            errs.append(f"bad CWE id {cwe!r}")
    return errs


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.validate_dataset <path.jsonl>")
        return 2
    path = Path(sys.argv[1])
    errs = validate(path)
    if errs:
        print(f"[FAIL] {path}: {len(errs)} issue(s)")
        for e in errs:
            print("  -", e)
        return 1
    print(f"[OK] {path}: all cases valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())