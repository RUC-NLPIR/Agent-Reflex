---
name: reproduce-acebench
description: Run the ACEBench agent subset (multi-step 20 + multi-turn 30) with the EnvScaler protocol.
---

# ACEBench (agent)

- **Code**: `interact_with_env/` is EnvScaler's evaluation harness
  ([RUC-NLPIR/EnvScaler](https://github.com/RUC-NLPIR/EnvScaler/tree/main/evaluation),
  license in `LICENSE.EnvScaler`), task data in `acebench_env/data/`.
- **Setup**: `bash ACEBench/setup.sh` (small Python 3.10 venv).
- **Run**: `RUN_NAME=<name> bash ACEBench/run.sh`.
- **Protocol** (EnvScaler): native FC, thinking on, agent temperature 0.7,
  user `gpt-4.1`, trajectories truncated at 20 steps (both subsets).
- **Score**: `summary.json` → (multi-step reward + multi-turn reward) / 50 × 100.
  `validate.py` checks that every expected id is present.
- **Note**: the same harness also runs τ-bench v1
  (`--env-name tau_bench_retail|tau_bench_airline`, 115 / 50 tasks) as in
  EnvScaler; the paper reports τ²-bench instead (`../Tau2`).
