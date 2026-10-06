#!/usr/bin/env python3
"""Validate a BFCL V4 run's status, traces, result coverage, and score tables."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


EXPECTED_ALL = 5217
EXPECTED_NON_WEB = 5017
EXPECTED_WEB = 200
SCORE_TABLES = (
    "data_overall.csv",
    "data_non_live.csv",
    "data_live.csv",
    "data_multi_turn.csv",
    "data_agentic.csv",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_result_ids(result_root: Path) -> tuple[int, int, list[str]]:
    ids: list[str] = []
    placeholders = 0
    files = 0
    for path in sorted(result_root.glob("**/*")):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".jsonl"}:
            continue
        files += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        placeholders += text.count("Error during inference")
        if path.suffix == ".jsonl" or "\n{" in text:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("id"):
                    ids.append(str(row["id"]))
        else:
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("id"):
                ids.append(str(row["id"]))
            elif isinstance(row, list):
                for item in row:
                    if isinstance(item, dict) and item.get("id"):
                        ids.append(str(item["id"]))
    return files, placeholders, ids


def overall_accuracy(score_dir: Path) -> dict[str, str]:
    path = score_dir / "data_overall.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    return {k: (v or "") for k, v in rows[-1].items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--root", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--max-placeholders", type=int, default=0)
    args = parser.parse_args()

    root = Path(args.root or Path(__file__).resolve().parents[1])
    run_root = root / "runs" / args.run_id
    status_path = run_root / "status.json"
    if not status_path.is_file():
        print(f"status missing: {status_path}", file=sys.stderr)
        return 2

    status = load_json(status_path)
    result_root = run_root / "project-root" / "result"
    score_dir = run_root / "project-root" / "score"
    files, placeholders, ids = count_result_ids(result_root)
    unique_ids = sorted(set(ids))
    suite = status.get("suite")
    expected = {
        "all": EXPECTED_ALL,
        "non-web": EXPECTED_NON_WEB,
        "web": EXPECTED_WEB,
    }.get(suite)

    missing_tables = [name for name in SCORE_TABLES if not (score_dir / name).is_file()]
    overall = overall_accuracy(score_dir)
    overall_acc = None
    for key, value in overall.items():
        if "overall" in key.lower() and "acc" in key.lower():
            try:
                overall_acc = float(value)
            except ValueError:
                overall_acc = value
            break

    failures: list[str] = []
    if status.get("execution_state") != "PASS":
        failures.append(f"execution_state={status.get('execution_state')}")
    if status.get("generate_exit") not in (0, None) and status.get("generate_exit") != 0:
        failures.append(f"generate_exit={status.get('generate_exit')}")
    if status.get("evaluate_exit") != 0:
        failures.append(f"evaluate_exit={status.get('evaluate_exit')}")
    if placeholders > args.max_placeholders:
        failures.append(f"placeholders={placeholders} > {args.max_placeholders}")
    if expected is not None and len(unique_ids) < expected:
        failures.append(f"unique_ids={len(unique_ids)} < expected {expected}")
    if missing_tables:
        failures.append("missing_score_tables=" + ",".join(missing_tables))
    if overall_acc in (None, "", 0, 0.0, "0", "0.0"):
        failures.append(f"overall_acc={overall_acc}")

    trace_failed = (status.get("trace") or {}).get("model_api_attempts_failed", 0)
    summary = {
        "run_id": args.run_id,
        "suite": suite,
        "model": status.get("model"),
        "execution_state": status.get("execution_state"),
        "trace_complete": status.get("trace_complete"),
        "generate_exit": status.get("generate_exit"),
        "evaluate_exit": status.get("evaluate_exit"),
        "result_files": files,
        "unique_result_ids": len(unique_ids),
        "expected_ids": expected,
        "placeholders": placeholders,
        "model_api_attempts_failed": trace_failed,
        "serper_calls_recorded": (status.get("trace") or {}).get("serper_calls_recorded"),
        "missing_score_tables": missing_tables,
        "overall_row": overall,
        "failures": failures,
        "state": "PASS" if not failures else "FAIL",
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.summary:
        Path(args.summary).write_text(text + "\n", encoding="utf-8")
    return 0 if not failures else 10


if __name__ == "__main__":
    raise SystemExit(main())
