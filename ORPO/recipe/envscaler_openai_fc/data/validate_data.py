"""Validate generated EnvScaler training and BFCL validation JSONL files."""

import argparse
import hashlib
import json
from pathlib import Path


def load_jsonl(path: str | Path) -> tuple[list[dict], str]:
    path = Path(path)
    digest = hashlib.sha256()
    rows = []
    with open(path, "rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            digest.update(raw)
            if raw.strip():
                try:
                    rows.append(json.loads(raw))
                except Exception as exc:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSON: {exc}"
                    ) from exc
    return rows, digest.hexdigest()


def validate_tool_schemas(tools: list, context: str) -> None:
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"{context}: tools must be a non-empty list")
    names = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if (
            not isinstance(tool, dict)
            or tool.get("type") != "function"
            or not isinstance(function, dict)
            or not function.get("name")
        ):
            raise ValueError(f"{context}: invalid OpenAI function schema")
        names.append(function["name"])
    if len(names) != len(set(names)):
        raise ValueError(f"{context}: duplicate tool names")


def validate_train(rows: list[dict], expected: int) -> None:
    if len(rows) != expected:
        raise ValueError(f"train row count: expected {expected}, got {len(rows)}")
    task_ids = []
    for index, row in enumerate(rows):
        if (
            row.get("data_source") != "envscaler"
            or row.get("agent_name") != "envscaler_openai_fc"
        ):
            raise ValueError(f"train[{index}]: invalid source or agent route")
        extra = row.get("extra_info") or {}
        environment = extra.get("environment") or {}
        verifier = extra.get("verifier") or {}
        task_ids.append(extra.get("task_id"))
        for key in ("class_name", "class_code", "initial_state", "tools"):
            if key not in environment:
                raise ValueError(f"train[{index}]: environment.{key} missing")
        if not isinstance(environment["initial_state"], dict):
            raise ValueError(f"train[{index}]: initial_state is not an object")
        validate_tool_schemas(environment["tools"], f"train[{index}]")
        checklist = verifier.get("checklist")
        if not isinstance(checklist, list) or not checklist:
            raise ValueError(f"train[{index}]: checklist missing")
    if None in task_ids or len(task_ids) != len(set(task_ids)):
        raise ValueError("training task IDs are missing or duplicated")


def validate_val(rows: list[dict], expected: int) -> None:
    if len(rows) != expected:
        raise ValueError(f"val row count: expected {expected}, got {len(rows)}")
    ids = []
    for index, row in enumerate(rows):
        if row.get("data_source") != "bfcl" or row.get("agent_name") != "bfcl_agent":
            raise ValueError(f"val[{index}]: invalid source or agent route")
        extra = row.get("extra_info") or {}
        ids.append(extra.get("id"))
        validate_tool_schemas(extra.get("tools"), f"val[{index}]")
    expected_ids = [f"multi_turn_base_{index}" for index in range(expected)]
    if ids != expected_ids:
        raise ValueError("BFCL validation IDs are not the fixed ordered 0..127 subset")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--expected-train", type=int, default=2550)
    parser.add_argument("--expected-val", type=int, default=128)
    args = parser.parse_args()

    train_rows, train_hash = load_jsonl(args.train)
    val_rows, val_hash = load_jsonl(args.val)
    validate_train(train_rows, args.expected_train)
    validate_val(val_rows, args.expected_val)
    print(f"[OK] train rows={len(train_rows)} sha256={train_hash}")
    print(f"[OK] val rows={len(val_rows)} sha256={val_hash}")


if __name__ == "__main__":
    main()
