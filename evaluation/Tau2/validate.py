#!/usr/bin/env python3
"""Validate a Tau2 results.json against the official base-split IDs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

INFRA = {
    "INFRASTRUCTURE_ERROR",
    "infrastructure_error",
    "UNEXPECTED_ERROR",
    "unexpected_error",
}


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    sims = data.get("simulations") or []
    return sims


def reward_of(row: dict) -> float:
    info = row.get("reward_info") or {}
    if isinstance(info, dict) and info.get("reward") is not None:
        return float(info["reward"])
    if row.get("reward") is not None:
        return float(row["reward"])
    return 0.0


def task_id_of(row: dict) -> str | None:
    tid = row.get("task_id") or row.get("id")
    return str(tid) if tid is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_file")
    parser.add_argument("--expected-ids", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    result_path = Path(args.result_file)
    expected_path = Path(args.expected_ids)
    if expected_path.exists():
        text = expected_path.read_text(encoding="utf-8").lstrip()
        if text.startswith("{") or text.startswith("["):
            raw = json.loads(text)
            if isinstance(raw, dict):
                expected_ids = [str(x) for x in (raw.get("ids") or raw.get("base") or [])]
            else:
                expected_ids = [str(x) for x in raw]
        else:
            expected_ids = [x.strip() for x in text.splitlines() if x.strip()]
    else:
        expected_ids = [x.strip() for x in args.expected_ids.split(",") if x.strip()]

    expected = set(expected_ids)
    rows = load_rows(result_path)
    by_id: dict[str, dict] = {}
    for row in rows:
        tid = task_id_of(row)
        if tid is not None:
            by_id[tid] = row

    missing = sorted(expected - set(by_id))
    extra = sorted(set(by_id) - expected)
    infra_failures = []
    reward_sum = 0.0
    terminated_ok = 0
    for tid, row in by_id.items():
        reward_sum += reward_of(row)
        reason = str(row.get("termination_reason") or "")
        blob = json.dumps(row, ensure_ascii=False)
        if (
            reason in INFRA
            or "Connection reset" in blob
            or "Failed to get response" in blob
            or "All chat completion endpoints failed" in blob
        ):
            infra_failures.append(tid)
        if reason in {"USER_STOP", "user_stop", "AGENT_STOP", "agent_stop"}:
            terminated_ok += 1

    failures = []
    if missing:
        failures.append(f"missing ids: {missing[:20]}{'...' if len(missing) > 20 else ''}")
    if extra:
        failures.append(f"extra ids: {extra[:20]}")
    if infra_failures:
        failures.append(f"infra failures: {infra_failures[:20]}")

    actual = len(by_id)
    expected_n = len(expected)
    status = "PASS"
    if actual != expected_n or missing or infra_failures:
        status = "FAIL"

    summary = {
        "result": str(result_path),
        "expected_tasks": expected_n,
        "actual_tasks": actual,
        "reward_sum": reward_sum,
        "score": 100.0 * reward_sum / actual if actual else None,
        "infra_failures": infra_failures,
        "terminated": terminated_ok,
        "status": status,
        "failures": failures,
    }
    Path(args.summary).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
