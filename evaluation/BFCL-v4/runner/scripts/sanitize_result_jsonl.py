#!/usr/bin/env python3
"""Drop empty/null-byte/invalid JSONL rows from BFCL result files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def sanitize_file(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    kept: list[bytes] = []
    dropped = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or b"\x00" in stripped:
            dropped += 1
            continue
        try:
            json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            dropped += 1
            continue
        kept.append(stripped)
    if dropped:
        path.write_bytes(b"\n".join(kept) + (b"\n" if kept else b""))
    return len(kept), dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True)
    args = parser.parse_args()
    total_dropped = 0
    for path in sorted(Path(args.result_dir).rglob("*_result.json")):
        kept, dropped = sanitize_file(path)
        if dropped:
            print(f"{path}: kept={kept} dropped={dropped}")
            total_dropped += dropped
    print(f"dropped_total={total_dropped}")


if __name__ == "__main__":
    main()
