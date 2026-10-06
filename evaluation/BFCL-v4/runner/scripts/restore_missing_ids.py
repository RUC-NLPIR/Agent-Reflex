#!/usr/bin/env python3
"""Fill missing result IDs from the original run so evaluate can score 5217."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_by_id(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not path.is_file():
        return rows
    for line in path.read_bytes().splitlines():
        stripped = line.strip()
        if not stripped or b"\x00" in stripped:
            continue
        try:
            row = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        test_id = row.get("id")
        if isinstance(test_id, str):
            rows[test_id] = row
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    args = parser.parse_args()
    src_root = Path(args.src)
    dst_root = Path(args.dst)
    restored = 0
    for dst in sorted(dst_root.rglob("*_result.json")):
        rel = dst.relative_to(dst_root)
        src = src_root / rel
        current = load_by_id(dst)
        original = load_by_id(src)
        missing = [k for k in original if k not in current]
        if not missing:
            continue
        for test_id in missing:
            current[test_id] = original[test_id]
            restored += 1
        ordered = sorted(
            current.values(),
            key=lambda row: (
                str(row.get("id", "")).rsplit("_", 1)[0],
                int(str(row.get("id", "0")).rsplit("_", 1)[-1])
                if str(row.get("id", "")).rsplit("_", 1)[-1].isdigit()
                else str(row.get("id", "")),
            ),
        )
        dst.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered),
            encoding="utf-8",
        )
        print(f"{rel}: restored {len(missing)} ids now={len(ordered)}")
    print(f"restored_total={restored}")


if __name__ == "__main__":
    main()
