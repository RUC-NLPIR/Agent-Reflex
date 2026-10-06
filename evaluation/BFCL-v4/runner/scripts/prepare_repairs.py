#!/usr/bin/env python3
"""Collect BFCL V4 inference placeholders into test_case_ids_to_generate.json."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def extract_category(test_id: str) -> str:
    return test_id.rsplit("_", 1)[0]


def is_placeholder(row: dict, only_http_status: bool = False) -> bool:
    result = row.get("result")
    if only_http_status:
        return isinstance(result, str) and "Error during inference: http_status" in result
    return bool(
        row.get("traceback")
        or (isinstance(result, str) and result.startswith("Error during inference"))
    )


def collect(result_dir: Path, only_http_status: bool = False) -> dict[str, list[str]]:
    failed: dict[str, set[str]] = defaultdict(set)
    for path in sorted(result_dir.rglob("*_result.json")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            test_id = row.get("id")
            if not isinstance(test_id, str):
                continue
            if is_placeholder(row, only_http_status=only_http_status):
                failed[extract_category(test_id)].add(test_id)
    return {
        category: sorted(
            ids,
            key=lambda item: int(item.rsplit("_", 1)[-1])
            if item.rsplit("_", 1)[-1].isdigit()
            else item,
        )
        for category, ids in failed.items()
        if ids
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--only-http-status",
        action="store_true",
        help="Only context-window / HTTP 400 placeholders, not transport timeouts.",
    )
    args = parser.parse_args()
    payload = collect(Path(args.result_dir), only_http_status=args.only_http_status)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(sum(len(ids) for ids in payload.values()))


if __name__ == "__main__":
    main()
