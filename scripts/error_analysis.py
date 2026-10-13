"""
Анализ провалов (Error Analysis) по ответам моделей на каждый кейс.

Читает results/predictions.jsonl (его пишет run_demo) и строит отчёт
results/error_analysis.md:
    T1 - на каких типах ошибок модель проваливается и что она ответила;
    T2 - какие CWE путает (эталон -> ответ) и где не нашла строку;
    T3 - почему не засчитан рефакторинг: упали тесты (каким исключением),
         код не стал проще или не парсится; для ловушек - код модели;
    итог - кейсы, на которых провалились ВСЕ реальные модели (раздел 5 задания).

Baseline-заглушки (читают эталон из промпта) в анализ не входят.

    python -m scripts.error_analysis
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS = ROOT / "results" / "predictions.jsonl"
REPORT = ROOT / "results" / "error_analysis.md"

MAX_CODE_LINES = 20


def load_records(path: Path = PREDICTIONS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _cell(value) -> str:
    """Значение для ячейки Markdown-таблицы: в одну строку, без поломки разметки."""
    text = str(value).replace("|", "\\|").replace("\n", " ⏎ ").strip()
    if not text:
        return "-"
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _pct(part: int, total: int) -> str:
    return f"{part}/{total} ({part / total:.0%})" if total else "-"


def t3_failure_reason(rec: dict) -> str:
    """Почему рефакторинг не засчитан - по-человечески."""
    parsed = rec.get("parsed") or {}
    if rec.get("error"):
        return f"ошибка запроса к модели: {rec['error'][:120]}"
    if not parsed.get("parseable"):
        return "код модели не парсится"
    if parsed.get("sandbox_error"):
        return f"тесты упали: {parsed['sandbox_error']}"
    before, after = parsed.get("complexity_before"), parsed.get("complexity_after")
    if before and after:
        return (f"тесты прошли, но код не стал проще: строк {before['loc']} → {after['loc']}, "
                f"узлов AST {before['ast_nodes']} → {after['ast_nodes']}")
    return "не засчитан"


def _section_t1(recs: list[dict]) -> list[str]:
    out = ["### T1 - ошибки статического анализа", ""]
    by_diff: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_diff[r["meta"].get("difficulty", "basic")].append(r)
    if "hard" in by_diff:
        out += ["| Сложность | Засчитано |", "|---|---:|"]
        out += [f"| {d} | {_pct(sum(r['passed'] for r in by_diff[d]), len(by_diff[d]))} |"
                for d in ("basic", "hard") if d in by_diff]
        out.append("")
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_type[r["expected"]["error_type"]].append(r)
    out += ["| Тип ошибки (эталон) | Тип угадан | Засчитано |", "|---|---:|---:|"]
    for etype, group in sorted(by_type.items(), key=lambda kv: sum(r["passed"] for r in kv[1]) / len(kv[1])):
        typed = sum(r["metrics"].get("type_accuracy", 0) == 1.0 for r in group)
        out.append(f"| {etype} | {_pct(typed, len(group))} | {_pct(sum(r['passed'] for r in group), len(group))} |")
    failed = [r for r in recs if not r["passed"]]
    off_format = [r for r in failed if not (r.get("parsed") or {}).get("error_type")]
    if failed:
        out += ["", "Проваленные кейсы:", "",
                "| Кейс | Эталон: тип | Ответ: тип | Эталон: fix | Ответ: fix | Замечание |",
                "|---|---|---|---|---|---|"]
        for r in failed:
            p = r.get("parsed") or {}
            note = "ответ не по формату: " + _cell(r.get("raw_output", "")[:80]) if r in off_format else ""
            out.append(f"| {r['case_id']} | {r['expected']['error_type']} | {_cell(p.get('error_type', ''))} "
                       f"| {_cell(r['expected']['fix'])} | {_cell(p.get('fix', ''))} | {note} |")
    if off_format:
        out += ["", f"Ответов не по формату (нет строки `TYPE:`): {len(off_format)}. "
                "Они не засчитаны: умение отвечать в заданном формате - часть задачи."]
    trapped = [r for r in failed if r["meta"].get("trap")]
    if trapped:
        out += ["", "**Ловушки, в которые попала модель:**", ""]
        out += [f"- **{r['case_id']}** - {r['meta']['trap']}" for r in trapped]
    return out + [""]


def _section_t2(recs: list[dict]) -> list[str]:
    out = ["### T2 - поиск уязвимостей", ""]
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_domain[r["meta"].get("domain", "?")].append(r)
    out += ["| Домен | CWE верный | Засчитано |", "|---|---:|---:|"]
    for domain, group in sorted(by_domain.items()):
        cwe_ok = sum(r["metrics"].get("cwe_accuracy", 0) == 1.0 for r in group)
        out.append(f"| {domain} | {_pct(cwe_ok, len(group))} | {_pct(sum(r['passed'] for r in group), len(group))} |")

    wrong_cwe = [r for r in recs if r["metrics"].get("cwe_accuracy", 0) < 1.0]
    out += ["", f"**Путаница CWE** - {len(wrong_cwe)} из {len(recs)} кейсов:", ""]
    if wrong_cwe:
        out += ["Колонка «Объяснение модели» показывает, поняла ли модель суть уязвимости, "
                "даже если номер CWE неверный.", "",
                "| Кейс | Домен | Эталон | Допустимо также | Ответ модели | Объяснение модели |",
                "|---|---|---|---|---|---|"]
        for r in wrong_cwe:
            alt = ", ".join(r["meta"].get("acceptable_cwe", [])) or "-"
            parsed = r.get("parsed") or {}
            answer = parsed.get("cwe") or "(не указан)"
            cause = (parsed.get("cause") or "").replace("|", "/")[:160] or "-"
            out.append(f"| {r['case_id']} | {r['meta'].get('domain', '?')} | {r['expected']['cwe']} "
                       f"| {alt} | {answer} | {cause} |")

    missed = [r for r in recs if r["metrics"].get("line_recall", 0) < 1.0
              or r["metrics"].get("line_precision", 0) < 0.5]
    out += ["", f"**Строки с уязвимостью найдены не полностью или с лишними** - {len(missed)} кейсов:", ""]
    if missed:
        out += ["| Кейс | Эталонные строки | Ответ модели |", "|---|---|---|"]
        for r in missed:
            out.append(f"| {r['case_id']} | {r['expected']['lines']} | {(r.get('parsed') or {}).get('lines', [])} |")
    return out + [""]


def _section_t3(recs: list[dict]) -> list[str]:
    out = ["### T3 - рефакторинг", ""]
    by_diff: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_diff[r["meta"].get("difficulty", "basic")].append(r)
    out += ["| Сложность | Тесты прошли | Засчитано |", "|---|---:|---:|"]
    for diff in ("basic", "hard"):
        group = by_diff.get(diff, [])
        tests = sum(r["metrics"].get("tests_pass", 0) == 1.0 for r in group)
        out.append(f"| {diff} | {_pct(tests, len(group))} | {_pct(sum(r['passed'] for r in group), len(group))} |")

    failed = [r for r in recs if not r["passed"]]
    if failed:
        out += ["", "Проваленные кейсы:", "",
                "| Кейс | Сложность | Паттерн | Причина |", "|---|---|---|---|"]
        for r in failed:
            out.append(f"| {r['case_id']} | {r['meta'].get('difficulty', '?')} "
                       f"| {r['meta'].get('pattern', '')} | {t3_failure_reason(r).replace('|', '/')} |")
    trapped = [r for r in failed if r["meta"].get("trap")]
    if trapped:
        out += ["", "**Ловушки, в которые попала модель:**", ""]
        for r in trapped:
            code = ((r.get("parsed") or {}).get("code") or "").splitlines()
            shown = "\n".join(code[:MAX_CODE_LINES]) + ("\n# ..." if len(code) > MAX_CODE_LINES else "")
            out += [f"**{r['case_id']}** - {r['meta'].get('pattern', '')}", "",
                    f"- Ловушка: {r['meta']['trap']}",
                    f"- Результат: {t3_failure_reason(r)}", "",
                    "Ответ модели:", "", "```python", shown, "```", ""]
    return out + [""]


_GROUP_KEY = {  # категории для «провалов всех моделей»
    "T1": lambda r: r["expected"].get("error_type", "?"),
    "T2": lambda r: r["expected"].get("cwe", "?"),
    "T3": lambda r: r["meta"].get("pattern", "?"),
}
_GROUP_TITLE = {"T1": "тип ошибки", "T2": "CWE", "T3": "паттерн"}


def _section_common(by_model: dict[str, list[dict]]) -> list[str]:
    """Кейсы, проваленные всеми реальными моделями, - по категориям."""
    n_models = len(by_model)
    out = ["## Провалы всех моделей", ""]
    if n_models == 1:
        out += ["Пока подключена одна реальная модель, поэтому здесь её провалы. "
                "С подключением второй модели останутся только кейсы, которые не "
                "решила ни одна.", ""]
    fails: Counter = Counter()
    sample: dict[tuple[str, str], dict] = {}
    for recs in by_model.values():
        for r in recs:
            if not r["passed"]:
                fails[(r["task"], r["case_id"])] += 1
                sample[(r["task"], r["case_id"])] = r
    common = [sample[k] for k, n in fails.items() if n == n_models]
    if not common:
        return out + ["Таких кейсов нет.", ""]
    for task in sorted({r["task"] for r in common}):
        groups = Counter(_GROUP_KEY[task](r) for r in common if r["task"] == task)
        out += [f"**{task}** - по категории «{_GROUP_TITLE[task]}»:", ""]
        out += [f"- {key}: {n}" for key, n in groups.most_common()]
        out.append("")
    return out


def build_report(records: list[dict]) -> str:
    real = [r for r in records if not r.get("baseline")]
    note = ""
    if not real:
        real = records
        note = "_Реальных моделей в прогоне нет - отчёт построен по baseline-заглушкам._\n"
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in real:
        by_model[r["model"]].append(r)

    out = ["# Анализ провалов (Error Analysis)", "",
           "Построено по `results/predictions.jsonl` - ответу каждой модели на каждый кейс.",
           "Baseline-заглушки не включены: они читают эталон из промпта.", ""]
    if note:
        out.append(note)
    sections = {"T1": _section_t1, "T2": _section_t2, "T3": _section_t3}
    for model, recs in by_model.items():
        out += [f"## {model}", ""]
        totals = Counter(r["task"] for r in recs)
        passed = Counter(r["task"] for r in recs if r["passed"])
        out += [", ".join(f"{t}: {_pct(passed[t], totals[t])}" for t in sorted(totals)), ""]
        for task in sorted(totals):
            if task in sections:
                out += sections[task]([r for r in recs if r["task"] == task])
    out += _section_common(by_model)
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    if not PREDICTIONS.exists():
        print(f"Нет {PREDICTIONS.relative_to(ROOT)} - сначала запустите python -m scripts.run_demo")
        return 1
    REPORT.write_text(build_report(load_records()), encoding="utf-8")
    print(f"[OK] {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
