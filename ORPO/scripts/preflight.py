"""Fail-fast checks for the initial checkpoint, data, agent routing, and tokenizer FC support."""

import argparse
import importlib
import json
import os

from transformers import AutoTokenizer

from recipe.envscaler_openai_fc.data.validate_data import (
    load_jsonl,
    validate_train,
    validate_val,
)
from scripts.prepare_init_checkpoint import config_fixes, tokenizer_fixes


def check_checkpoint(model_path: str) -> None:
    if not os.path.isdir(model_path):
        return
    with open(os.path.join(model_path, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    with open(os.path.join(model_path, "tokenizer_config.json"), encoding="utf-8") as f:
        tok = json.load(f)
    if config_fixes(cfg) or tokenizer_fixes(tok):
        raise RuntimeError(
            f"{model_path} was saved by transformers 5.x; run\n"
            f"  python scripts/prepare_init_checkpoint.py {model_path} --apply"
        )
    theta = cfg.get("rope_theta")
    if theta is None or float(theta) < 1e5:
        raise RuntimeError(f"refusing to train: rope_theta={theta} in {model_path}/config.json")
    print(f"[OK] checkpoint rope_theta={theta} torch_dtype={cfg.get('torch_dtype')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--max-prompt-length", type=int, required=True)
    args = parser.parse_args()

    check_checkpoint(args.model_path)
    train, train_hash = load_jsonl(args.train)
    val, val_hash = load_jsonl(args.val)
    if len(train) < 256:
        raise ValueError(f"train set too small for RL: {len(train)}")
    validate_train(train, len(train))
    validate_val(val, 128)

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    sample = train[0]
    tools = sample["extra_info"]["environment"]["tools"]
    prompt = sample["prompt"]
    prompt_ids = tokenizer.apply_chat_template(
        prompt,
        tools=tools,
        add_generation_prompt=True,
        tokenize=True,
    )
    call_id = "call_preflight_00"
    messages = prompt + [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tools[0]["function"]["name"],
                        "arguments": "{}",
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps({"ok": True})},
    ]
    trajectory_ids = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=True,
        tokenize=True,
    )
    if not prompt_ids or len(trajectory_ids) <= len(prompt_ids):
        raise RuntimeError(
            "tokenizer chat template did not serialize the FC/tool-result turn"
        )

    longest = {"train": (0, ""), "val": (0, "")}
    for split, rows in (("train", train), ("val", val)):
        for row in rows:
            extra = row["extra_info"]
            row_tools = (
                extra["environment"]["tools"]
                if row["data_source"] == "envscaler"
                else extra["tools"]
            )
            length = len(
                tokenizer.apply_chat_template(
                    row["prompt"],
                    tools=row_tools,
                    add_generation_prompt=True,
                    tokenize=True,
                )
            )
            task_id = extra.get("task_id", extra.get("id", "unknown"))
            if length > longest[split][0]:
                longest[split] = (length, task_id)
            if length > args.max_prompt_length:
                raise RuntimeError(
                    f"{split} task {task_id} has {length} prompt tokens, "
                    f"over max_prompt_length={args.max_prompt_length}"
                )

    module = importlib.import_module("recipe.envscaler_openai_fc.agent_loop")
    if not hasattr(module, "EnvScalerOpenAIFCAgentLoop"):
        raise RuntimeError("EnvScalerOpenAIFCAgentLoop import failed")
    print(f"[OK] train={len(train)} sha256={train_hash}")
    print(f"[OK] val=128 sha256={val_hash}")
    print(
        f"[OK] tokenizer native FC prompt_tokens={len(prompt_ids)} trajectory_tokens={len(trajectory_ids)}"
    )
    print(
        f"[OK] all prompts fit max_prompt_length={args.max_prompt_length}; "
        f"train_max={longest['train']} val_max={longest['val']}"
    )
    print("[OK] agent route envscaler_openai_fc is importable")


if __name__ == "__main__":
    main()
