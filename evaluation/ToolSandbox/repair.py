#!/usr/bin/env python3
"""List or merge ToolSandbox failed scenarios into an existing result_summary.json."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def has_conversion_syntax_error(summary_path: Path, scenario_name: str) -> bool:
    context_path = summary_path.parent / "trajectories" / scenario_name / "execution_context.json"
    if not context_path.exists():
        return False
    sandbox_rows = load(context_path).get("_dbs", {}).get("SANDBOX", [])
    return any(
        "SyntaxError" in str(row.get("tool_call_exception") or "")
        for row in sandbox_rows
    )


def failed_names(summary: dict, summary_path: Path) -> list[str]:
    skip = {"TimeoutError", "TaskTimeout"}
    return [
        item["name"]
        for item in summary.get("per_scenario_results", [])
        if item.get("exception_type") not in skip
        and (
            item.get("traceback")
            or has_conversion_syntax_error(summary_path, item["name"])
        )
    ]


def merge(base: dict, patch: dict) -> dict:
    by_name = {item["name"]: item for item in patch.get("per_scenario_results", [])}
    merged = []
    for item in base.get("per_scenario_results", []):
        replacement = by_name.get(item["name"])
        merged.append(replacement if replacement is not None else item)
    base["per_scenario_results"] = merged
    base["category_aggregated_results"] = aggregate_results(merged)
    return base


def aggregate_results(results: list[dict]) -> dict[str, dict[str, float]]:
    augmented_categories = {
        "TOOL_NAME_SCRAMBLED",
        "TOOL_DESCRIPTION_SCRAMBLED",
        "ARG_DESCRIPTION_SCRAMBLED",
        "ARG_TYPE_SCRAMBLED",
        "ARG_NAME_SCRAMBLED",
    }
    values: dict[str, dict[str, list[float]]] = {}
    for item in results:
        categories = set(item.get("categories", []))
        for category in categories:
            if category == "THREE_DISTRACTION_TOOLS" and categories & augmented_categories:
                continue
            bucket = values.setdefault(category, {"similarity": [], "turn_count": []})
            bucket["similarity"].append(float(item["similarity"]))
            bucket["turn_count"].append(float(item["turn_count"]))
        overall = values.setdefault(
            "ALL_CATEGORIES", {"similarity": [], "turn_count": []}
        )
        overall["similarity"].append(float(item["similarity"]))
        overall["turn_count"].append(float(item["turn_count"]))
    return {
        category: {
            metric: sum(metric_values) / len(metric_values)
            for metric, metric_values in metrics.items()
        }
        for category, metrics in values.items()
    }


def copy_trajectories(base_path: Path, patch_path: Path, scenario_names: list[str]) -> None:
    for name in scenario_names:
        source = patch_path.parent / "trajectories" / name
        target = base_path.parent / "trajectories" / name
        if source.exists():
            shutil.copytree(source, target, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--merge-from")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    summary = load(summary_path)
    names = failed_names(summary, summary_path)
    print("failed", len(names))
    for name in names:
        print(name)

    if args.merge_from:
        patch_path = Path(args.merge_from)
        patch = load(patch_path)
        replacement_names = [
            item["name"] for item in patch.get("per_scenario_results", [])
        ]
        summary = merge(summary, patch)
        if args.write:
            copy_trajectories(summary_path, patch_path, replacement_names)
        remaining = failed_names(summary, summary_path)
        print("remaining", len(remaining))
        if args.write:
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
