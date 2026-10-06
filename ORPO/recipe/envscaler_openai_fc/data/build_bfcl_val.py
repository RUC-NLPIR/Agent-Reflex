"""Build the fixed BFCL multi-turn validation subset (IDs 0 through 127)."""

import argparse
import json
from pathlib import Path

BFCL_SYSTEM_PROMPT = (
    "You are a helpful assistant. When given a specific task, your goal is to complete it "
    "in an interactive environment by making step-by-step use of available tools. \n"
    "- Before completing the task, at each step, select a tool from the tool list and fill "
    "in all required parameters, making sure that the values are valid. "
    "Avoid making parallel tool calls in one step.\n"
    "- When you believe the task has been completed, respond only with 'Task Completed' "
    "to end the trajectory, without adding any other content or making any tool calls.\n"
    "- It is recommended to first call query tools to gather sufficient information, "
    "then use modification tools to complete the task. Adjust actions promptly based on "
    "the feedback from the environment, i.e., the tool results.\n"
)


def convert_sample(sample: dict) -> dict:
    return {
        "prompt": [
            {"role": "system", "content": BFCL_SYSTEM_PROMPT},
            {"role": "user", "content": sample["questions"][0]},
        ],
        "data_source": "bfcl",
        "agent_name": "bfcl_agent",
        "reward_model": {"style": "rule", "ground_truth": None},
        "ability": "tool_use",
        "extra_info": {
            "id": sample["id"],
            "questions": sample["questions"],
            "answers": sample["answers"],
            "initial_config": sample["initial_config"],
            "involved_classes": sample["involved_classes"],
            "tools": sample["tools"],
        },
    }


def build_rows(samples: list[dict], limit: int = 128) -> list[dict]:
    expected_ids = [f"multi_turn_base_{index}" for index in range(limit)]
    by_id = {sample["id"]: sample for sample in samples}
    missing = [task_id for task_id in expected_ids if task_id not in by_id]
    if missing:
        raise KeyError(f"BFCL source is missing expected IDs: {missing[:5]}")
    return [convert_sample(by_id[task_id]) for task_id in expected_ids]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    default_source = (
        repo_root
        / "verl/experimental/agent_loop/bfcl_env/data/data_multi_turn_base.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(default_source))
    parser.add_argument("--output", default="data/generated/bfcl_val_128.jsonl")
    parser.add_argument("--limit", type=int, default=128)
    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as handle:
        samples = json.load(handle)
    rows = build_rows(samples, args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[OK] wrote {len(rows)} BFCL validation rows to {output}")


if __name__ == "__main__":
    main()
