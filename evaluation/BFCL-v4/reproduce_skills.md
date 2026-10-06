---
name: reproduce-bfcl-v4
description: Run BFCL v4 all_scoring (5,217 cases) for an Agent-Reflex checkpoint.
---

# BFCL v4

- **Setup**: `bash BFCL-v4/setup.sh` builds `runner/.venv` with the official
  `bfcl_eval` from gorilla `6ea5797`, installed with the test set shipped in
  `BFCL-v4/data/`, plus the `bfcl_boyue` adapter (OpenAI-compatible FC
  handler for the local vLLM, Serper instead of SerpAPI for web search).
- **Serve** with `shared/serve_vllm.sh` (40,960 context, as for the other benches).
- **Run**: `RUN_NAME=<name> bash BFCL-v4/run.sh` (needs `SERPER_API_KEY`).
  `BFCL_SUITE=non-web` skips web search.
- **Protocol**: registry `local-qwen3-8b-FC`, temperature 0.001 (BFCL
  default), 120 threads.
- **Score**: `outputs/bfcl-v4/<run_id>/data_overall.csv`, official weights
  (10% Non-Live, 10% Live, 10% Irrelevance, 30% Multi-Turn, 40% Agentic).
- **Repair**: transport errors leave `Error during inference` placeholders,
  which the scorer counts as wrong. `run.sh` regenerates exactly those ids
  (same model and settings, up to 3 passes) before scoring;
  `validation.json` reports what is left.
