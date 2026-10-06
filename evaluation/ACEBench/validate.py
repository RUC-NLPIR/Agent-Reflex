#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

THINKING_RE = re.compile(r"reasoning_content|")


def parse_expected_ids(spec: str):
    if spec.startswith("range:"):
        _, bounds = spec.split(":", 1)
        start, end = bounds.split(":")
        return [str(i) for i in range(int(start), int(end))]
    if spec.startswith("prefix:"):
        _, rest = spec.split(":", 1)
        prefix, count = rest.rsplit(":", 1)
        return [f"{prefix}{i}" for i in range(int(count))]
    return [x.strip() for x in spec.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_file")
    parser.add_argument("--expected-ids", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    result_path = Path(args.result_file)
    expected_ids = set(parse_expected_ids(args.expected_ids))
    rows = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
    by_id = {}
    for row in rows:
        tid = next(
            (row.get(key) for key in ("_eval_task_id", "task_id", "id") if row.get(key) is not None),
            None,
        )
        if tid is not None:
            by_id[str(tid)] = row

    missing = sorted(expected_ids - set(by_id))
    extra = sorted(set(by_id) - expected_ids)
    infra_failures = []
    missing_thinking = []
    malformed = []
    reward_sum = 0.0
    terminated = truncated = 0

    for tid, row in by_id.items():
        reward_sum += float(row.get("total_reward", 0) or 0)
        if row.get("terminated"):
            terminated += 1
        if row.get("truncated"):
            truncated += 1
        blob = json.dumps(row, ensure_ascii=False)
        if "Connection reset" in blob or "Failed to get response" in blob or "All chat completion endpoints failed" in blob:
            infra_failures.append(tid)
        if not THINKING_RE.search(blob):
            missing_thinking.append(tid)

    failures = []
    if missing:
        failures.append(f"missing ids: {missing[:20]}{'...' if len(missing) > 20 else ''}")
    if extra:
        failures.append(f"extra ids: {extra[:20]}")
    if infra_failures:
        failures.append(f"infra failures: {infra_failures[:20]}")

    actual = len(by_id)
    expected = len(expected_ids)
    status = "PASS"
    if actual != expected or missing or infra_failures:
        status = "FAIL"
    if not missing and actual == expected and infra_failures:
        status = "FAIL"

    summary = {
        "result": str(result_path),
        "expected_tasks": expected,
        "actual_tasks": actual,
        "reward_sum": reward_sum,
        "score": 100.0 * reward_sum / actual if actual else None,
        "infra_failures": infra_failures,
        "missing_thinking_task_ids": missing_thinking,
        "malformed_task_ids": malformed,
        "terminated": terminated,
        "truncated": truncated,
        "status": status,
        "failures": failures,
    }
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
