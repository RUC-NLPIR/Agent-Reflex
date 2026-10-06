"""
Batch interactive evaluation entrypoint for EnvScaler environments.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from dotenv import load_dotenv

from agent.task_solve_agent import TaskSolveAgent
from acebench_env import AceBenchMultiStepEnv, AceBenchMultiTurnEnv
from taubench_env import TauBenchAirlineEnv, TauBenchRetailEnv

ENV_CLS_MAP = {
    "tau_bench_retail": TauBenchRetailEnv,
    "tau_bench_airline": TauBenchAirlineEnv,
    "acebench_multi_step": AceBenchMultiStepEnv,
    "acebench_multi_turn": AceBenchMultiTurnEnv,
}

MAX_STEPS_MAP = {
    "tau_bench_retail": 30,
    "tau_bench_airline": 30,
    "acebench_multi_step": 20,
    "acebench_multi_turn": 20,
}


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for item in value:
            items.extend(split_values(item))
        return items
    text = str(value).strip()
    if not text:
        return []
    return [item for item in text.replace(",", " ").split() if item]


def configure_runtime_env(args: argparse.Namespace) -> None:
    agent_urls = split_values(args.agent_base_urls)
    user_urls = split_values(args.user_base_urls)
    if agent_urls:
        os.environ["OPENAI_BASE_URL"] = agent_urls[0]
        os.environ["OPENAI_BASE_URLS"] = ",".join(agent_urls)
        os.environ["AGENT_BASE_URL"] = agent_urls[0]
        os.environ["AGENT_BASE_URLS"] = ",".join(agent_urls)
    if args.agent_api_key:
        os.environ["OPENAI_API_KEY"] = args.agent_api_key
        os.environ["AGENT_API_KEY"] = args.agent_api_key
    if user_urls:
        os.environ["USER_OPENAI_BASE_URL"] = user_urls[0]
        os.environ["USER_OPENAI_BASE_URLS"] = ",".join(user_urls)
    if args.user_api_key:
        os.environ["USER_OPENAI_API_KEY"] = args.user_api_key
    if args.vllm_max_attempts_per_client:
        os.environ["VLLM_MAX_ATTEMPTS_PER_CLIENT"] = str(args.vllm_max_attempts_per_client)


def build_env_config(env_name: str, user_model: str, user_provider: str) -> dict[str, Any]:
    if env_name in {"tau_bench_retail", "tau_bench_airline"}:
        return {
            "mode": "eval",
            "user_model": user_model,
            "user_strategy": "llm_react",
            "user_provider": user_provider,
        }
    if env_name == "acebench_multi_step":
        return {"domain": "agent_multi_step", "truncated_steps": 20}
    if env_name == "acebench_multi_turn":
        return {
            "domain": "agent_multi_turn",
            "truncated_steps": 20,
            "user_model": user_model,
            "user_provider": user_provider,
        }
    raise ValueError(f"Unsupported env_name: {env_name}")


def resolve_task_ids(args: argparse.Namespace) -> list[int | str]:
    if args.task_ids:
        ids: list[int | str] = []
        for item in split_values(args.task_ids):
            if item.isdigit():
                ids.append(int(item))
            else:
                ids.append(item)
        return ids
    if args.task_start is not None and args.task_end is not None:
        return list(range(args.task_start, args.task_end))
    raise ValueError("Either --task-ids or --task-start/--task-end is required")


def solve_task(
    env_name: str,
    env_config: dict[str, Any],
    agent_model: str,
    agent_model_provider: str,
    infer_mode: str,
    enable_thinking: bool,
    temperature: float,
    task_id: int | str,
) -> dict[str, Any]:
    env_cls = ENV_CLS_MAP[env_name]
    env = env_cls(**env_config)
    agent = TaskSolveAgent(
        env_name=env_name,
        env=env,
        model=agent_model,
        provider=agent_model_provider,
        infer_mode=infer_mode,
        temperature=temperature,
        max_steps=MAX_STEPS_MAP[env_name],
        enable_thinking=enable_thinking,
    )
    result = agent.run(task_index=task_id)
    result["_eval_task_id"] = task_id
    return result


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-name", required=True)
    parser.add_argument("--agent-model", required=True)
    parser.add_argument("--agent-model-provider", default="openai")
    parser.add_argument("--agent-api-key", default=None)
    parser.add_argument("--agent-base-urls", nargs="*", default=None)
    parser.add_argument("--user-model", default="gpt-4.1")
    parser.add_argument("--user-model-provider", default="openai")
    parser.add_argument("--user-api-key", default=None)
    parser.add_argument("--user-base-urls", nargs="*", default=None)
    parser.add_argument("--infer-mode", default="fc", choices=["fc", "prompt"])
    parser.add_argument("--enable-thinking", default="true")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--num-workers", type=int, default=1)
    parser.add_argument("--task-start", type=int, default=None)
    parser.add_argument("--task-end", type=int, default=None)
    parser.add_argument("--task-ids", default=None)
    parser.add_argument("--save-file-path", required=True)
    parser.add_argument("--vllm-max-attempts-per-client", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    configure_runtime_env(args)

    env_name = args.env_name
    env_config = build_env_config(env_name, args.user_model, args.user_model_provider)
    task_ids = resolve_task_ids(args)
    enable_thinking = parse_bool(args.enable_thinking)

    results: list[dict[str, Any]] = []
    workers = max(1, args.num_workers)
    if workers == 1:
        for task_id in task_ids:
            results.append(
                solve_task(
                    env_name=env_name,
                    env_config=env_config,
                    agent_model=args.agent_model,
                    agent_model_provider=args.agent_model_provider,
                    infer_mode=args.infer_mode,
                    enable_thinking=enable_thinking,
                    temperature=args.temperature,
                    task_id=task_id,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    solve_task,
                    env_name,
                    env_config,
                    args.agent_model,
                    args.agent_model_provider,
                    args.infer_mode,
                    enable_thinking,
                    args.temperature,
                    task_id,
                ): task_id
                for task_id in task_ids
            }
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda item: str(item.get("_eval_task_id")))
    save_json(args.save_file_path, results)
    print(f"Saved {len(results)} tasks to {args.save_file_path}")


if __name__ == "__main__":
    main()
