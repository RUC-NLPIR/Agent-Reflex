"""Build all 2,550 official EnvScaler RL tasks into VeRL JSONL."""

import argparse
import json
from pathlib import Path

from recipe.envscaler_openai_fc.prompt import build_prompt


def read_json(path: str | Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def normalize_initial_state(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise TypeError(
        f"init_config must be a dict or a JSON-object string, got {type(value).__name__}"
    )


def index_environment_metadata(metadata: dict) -> dict[str, dict]:
    indexed = {}
    for value in metadata.values():
        env_id = value["env_id"]
        if env_id in indexed:
            raise ValueError(f"duplicate env_id in environment metadata: {env_id}")
        indexed[env_id] = value
    return indexed


def convert_task(task: dict, env_metadata: dict, index: int) -> dict:
    environment = {
        "env_id": task["env_id"],
        "class_name": task["env_class_name"],
        "class_code": env_metadata["env_class_code"],
        "initial_state": normalize_initial_state(task["init_config"]),
        "tools": env_metadata["tools"],
    }
    verifier = {"kind": "checklist_func", "checklist": task["checklist_with_func"]}
    return {
        "prompt": build_prompt(task.get("task", ""), env_metadata),
        "data_source": "envscaler",
        "agent_name": "envscaler_openai_fc",
        "reward_model": {"style": "rule", "ground_truth": None},
        "ability": "tool_use",
        "extra_info": {
            "index": index,
            "task_id": task["task_id"],
            "env_id": task["env_id"],
            "environment": environment,
            "verifier": verifier,
        },
    }


def build_rows(tasks: list[dict], metadata: dict) -> list[dict]:
    env_by_id = index_environment_metadata(metadata)
    seen = set()
    rows = []
    for task in tasks:
        task_id = task["task_id"]
        if task_id in seen:
            raise ValueError(f"duplicate task_id: {task_id}")
        seen.add(task_id)
        env_id = task["env_id"]
        if env_id not in env_by_id:
            raise KeyError(f"task {task_id} references missing env_id {env_id}")
        rows.append(convert_task(task, env_by_id[env_id], len(rows)))
    return rows


def write_jsonl(rows: list[dict], output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-file", required=True)
    parser.add_argument("--env-meta-file", required=True)
    parser.add_argument("--output", default="data/generated/train_envscaler_2550.jsonl")
    parser.add_argument("--expected-rows", type=int, default=2550)
    args = parser.parse_args()

    tasks = read_json(args.scenario_file)
    metadata = read_json(args.env_meta_file)
    if not isinstance(tasks, list) or not isinstance(metadata, dict):
        raise TypeError(
            "scenario file must be a list and environment metadata must be an object"
        )
    rows = build_rows(tasks, metadata)
    if len(rows) != args.expected_rows:
        raise RuntimeError(f"expected {args.expected_rows} rows, built {len(rows)}")
    write_jsonl(rows, args.output)
    size = Path(args.output).stat().st_size
    print(
        f"[OK] wrote {len(rows)} EnvScaler rows to {args.output} ({size / 2**20:.1f} MiB)"
    )


if __name__ == "__main__":
    main()
