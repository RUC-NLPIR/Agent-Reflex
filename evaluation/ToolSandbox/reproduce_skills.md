---
name: reproduce-toolsandbox
description: Run ToolSandbox (200 offline scenarios) for an Agent-Reflex checkpoint.
---

# ToolSandbox

- **Setup**: `bash ToolSandbox/setup.sh` clones apple/ToolSandbox at
  `c8571d7` (the scenarios are Python code in that repository) and applies
  `toolsandbox_agent_reflex.patch`, which adds an OpenAI-compatible
  `Qwen3_8B` agent role (local vLLM, thinking on) and a `GPT_4_1` user role,
  both configured from the environment. It pins `httpx==0.27.2`: upstream's
  `openai==1.17.0` fails on httpx 0.28 (`unexpected keyword argument 'proxies'`).
- **Run**: `RUN_NAME=<name> bash ToolSandbox/run.sh`. Smoke: `TOOLSANDBOX_N=5`.
- **Protocol**: the first 200 scenarios that need no RapidAPI tools
  (`list_offline_scenarios.py`), agent temperature 0.6, top-p 0.95, top-k 20
  (Qwen3 thinking defaults), user `gpt-4.1`.
- **Score**: `summary.json` → mean similarity × 100 and the exception rate.
- **Repair**: scenarios that crashed with a traceback (transport errors) are
  re-run with the same settings, up to 3 passes, and merged back by
  `repair.py`. The optional per-scenario limit `EVAL_TASK_TIMEOUT` is off
  by default.
