"""
Пересчёт результатов по сохранённым ответам моделей — без новых запросов.

Когда меняется оценка (парсер ответа, метрика), гонять модели заново не
нужно: их ответы уже лежат в results/predictions.jsonl. Скрипт заново
оценивает эти ответы текущим кодом и перезаписывает leaderboard.txt,
run.json, predictions.jsonl и error_analysis.md.

T1 и T2 оцениваются заново. T3 берётся из сохранённых результатов как
есть: его оценка — запуск кода в Docker, а код модели от пересчёта не
меняется.

Заодно это проверка воспроизводимости: на ответах, которые оценка не
затрагивает (baseline'ы, T2), пересчёт обязан дать те же цифры.

    python -m scripts.rescore
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from scripts.error_analysis import build_report
from src.evaluator import SCORERS, aggregate, case_record, format_leaderboard
from src.schema import CaseResult, Prediction
from src.tasks.task1_lint import load_cases

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DATASETS = [
    ROOT / "data" / "task1_lint" / "samples.jsonl",
    ROOT / "data" / "task2_security" / "samples.jsonl",
    ROOT / "data" / "task3_refactor" / "samples.jsonl",
]
RESCORED_TASKS = {"T1", "T2"}


def rescore(records: list[dict]) -> tuple[list, list[dict]]:
    """(строки лидерборда, обновлённые записи) по сохранённым ответам."""
    cases = {c.case_id: c for path in DATASETS for c in load_cases(path)}
    per_model: dict[str, tuple[dict, dict]] = {}  # model -> (per_task, latencies)
    new_records: list[dict] = []
    for rec in records:
        per_task, latencies = per_model.setdefault(rec["model"], ({}, {}))
        if rec["task"] in RESCORED_TASKS:
            case = cases[rec["case_id"]]
            pred = Prediction(case_id=rec["case_id"], model_name=rec["model"],
                              raw_output=rec["raw_output"], latency_ms=rec["latency_ms"],
                              error=rec["error"])
            result = SCORERS[rec["task"]](case, pred)
            model = SimpleNamespace(name=rec["model"], needs_oracle=rec["baseline"])
            rec = case_record(case, model, pred, result)
        else:
            result = CaseResult(case_id=rec["case_id"], model_name=rec["model"],
                                task=rec["task"], metrics=rec["metrics"], passed=rec["passed"])
        new_records.append(rec)
        per_task.setdefault(rec["task"], []).append(result)
        latencies.setdefault(rec["task"], []).append(rec["latency_ms"])
    rows = []
    for model_name, (per_task, latencies) in per_model.items():
        rows += aggregate(model_name, per_task, latencies)
    return rows, new_records


def main() -> int:
    pred_path = RESULTS / "predictions.jsonl"
    if not pred_path.exists():
        print("Нет results/predictions.jsonl — сначала запустите python -m scripts.run_demo")
        return 1
    records = [json.loads(line) for line in pred_path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    rows, new_records = rescore(records)
    table = format_leaderboard(rows)
    print(table)

    run_json = RESULTS / "run.json"
    previous = json.loads(run_json.read_text(encoding="utf-8")) if run_json.exists() else {}
    from dataclasses import asdict
    payload = {
        "run_at": previous.get("run_at"),  # когда модели отвечали
        "rescored_at": datetime.now().isoformat(timespec="seconds"),
        "n_cases": len({r["case_id"] for r in new_records}),
        "rows": [asdict(r) for r in rows],
    }
    (RESULTS / "leaderboard.txt").write_text(table, encoding="utf-8")
    run_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pred_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new_records),
                         encoding="utf-8")
    (RESULTS / "error_analysis.md").write_text(build_report(new_records), encoding="utf-8")
    print("\nПересчитано по сохранённым ответам: results/ обновлены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
