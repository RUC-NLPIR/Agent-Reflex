---
name: reproduce-agent-reflex-eval
description: Evaluate an Agent-Reflex checkpoint on Tau2, BFCL-v4, ACEBench, VitaBench, AgentNoiseBench and ToolSandbox. Use when scoring a checkpoint or checking that the eval stack works.
---

# Reproduce the evaluation

## Steps

1. **Key**: register at https://api.boyuerichdata.opensphereai.com, create an
   `sk-…` token (group `auto`) on the API令牌 page, then `cp .env.example .env`
   and fill `BOYUE_API_KEY` (and `SERPER_API_KEY` from serper.dev for BFCL). Or keep it elsewhere and export `ENV_FILE=/path/to/file`.
   Never print or commit this file.
2. **Environments**: run `shared/setup_vllm.sh` and every `<Bench>/setup.sh`
   once. They need GitHub and PyPI access (export a proxy if needed).
3. **Serve** on an 8-GPU node:
   `MODEL_PATH=<hf_dir> bash shared/serve_vllm.sh` (40,960 context for every
   bench). Keep `MODEL_PATH` exported: each
   bench refuses to run if `/v1/models` reports a different root.
4. **Run** the full benchmarks:
   `MODEL_PATH=<hf_dir> RUN_NAME=<name> bash run_all.sh` (serves the model,
   then every bench), or one at a time with `RUN_NAME=<name> bash <Bench>/run.sh`.
5. Read `outputs/<bench>/<RUN_NAME>-<tag>/summary.json`. `status: FAIL` with
   a zero score means the harness is broken; fix it before trusting numbers.

## Protocol (keep it)

- Native function calling, thinking on (force-thinking template), vLLM TP 8.
- Agent temperature: Tau2 0.0, VitaBench 0.0, BFCL 0.001, ACEBench 0.7,
  ToolSandbox 0.6 / top-p 0.95 / top-k 20.
- User simulator `gpt-4.1` (= `gpt-4.1-2025-04-14`), VitaBench judge
  `claude-sonnet-4-6`.
- 120 concurrent tasks, 10 retries of the same request, no per-task time
  limit, no fallback model, no context truncation.

## Pitfalls

- The proxy must not see `127.0.0.1`; `shared/env.sh` sets `NO_PROXY`.
  On nodes where the gateway is only reachable through a proxy, export
  `HTTP_PROXY`/`HTTPS_PROXY` before running.
- With a proxy set, add your internal PyPI mirror to `NO_PROXY` too, or large
  wheel downloads stall.
- vLLM 0.27 needs Python 3.12 (its flashinfer import fails on 3.10);
  `shared/setup_vllm.sh` builds that venv with uv-managed Python.
- Do not raise `MAX_MODEL_LEN` past 40,960: Qwen3's rotary table ends there
  and longer sequences crash the server with a device-side assert.
- An empty or truncated summary usually means the gateway rejected the user
  model; check the bench log for HTTP 4xx before re-running.
- Re-running with the same `RUN_NAME` and `RUN_TAG` resumes Tau2 and
  VitaBench instead of starting over.
- Per-bench details: `<Bench>/reproduce_skills.md`.
