#!/usr/bin/env python3
"""Run one official tau2 domain (base split) against the local vLLM agent and a gpt-4.1 user."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tau2.data_model.simulation import TextRunConfig
from tau2.run import run_domain


def main() -> None:
    domain, save_to = sys.argv[1], sys.argv[2]
    retry = int(os.environ.get("RETRY", "10"))
    timeout = float(os.environ.get("TAU2_LLM_TIMEOUT", "1800"))
    # Upstream applies num_tasks before the split filter, so take the first N
    # base-split ids explicitly.
    num_tasks = os.environ.get("TAU2_NUM_TASKS")
    expected = json.loads((Path(__file__).parent / "expected_ids.json").read_text())
    task_ids = expected[domain][: int(num_tasks)] if num_tasks else None
    user_args = {
        "api_base": os.environ["USER_OPENAI_BASE_URL"],
        "api_key": os.environ["USER_OPENAI_API_KEY"],
        "temperature": 0.0,
        "num_retries": retry,
        "timeout": timeout,
    }
    agent_args = {
        "api_base": os.environ.get("TAU2_AGENT_API_BASE", "http://127.0.0.1:8000/v1"),
        "api_key": "EMPTY",
        "temperature": float(os.environ.get("AGENT_TEMPERATURE", "0.0")),
        "num_retries": retry,
        "timeout": timeout,
    }
    config = TextRunConfig(
        domain=domain,
        task_split_name="base",
        task_ids=task_ids,
        agent="llm_agent",
        llm_agent=f"openai/{os.environ.get('SERVED_MODEL_NAME', 'Qwen/Qwen3-8B')}",
        llm_args_agent=agent_args,
        user="user_simulator",
        llm_user=f"openai/{os.environ.get('USER_MODEL', 'gpt-4.1')}",
        llm_args_user=user_args,
        num_trials=1,
        max_concurrency=int(os.environ.get("MAX_CONCURRENCY", "120")),
        max_retries=retry,
        save_to=save_to,
        auto_resume=True,
        seed=300,
        log_level=os.environ.get("TAU2_LOG_LEVEL", "ERROR"),
    )
    results = run_domain(config)
    reward = sum(
        s.reward_info.reward for s in results.simulations if s.reward_info and s.reward_info.reward is not None
    )
    print(f"__TAU2_DOMAIN_DONE__ domain={domain} n={len(results.simulations)} reward_sum={reward:.4f}")


if __name__ == "__main__":
    main()
