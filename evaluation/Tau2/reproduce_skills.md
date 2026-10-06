---
name: reproduce-tau2
description: Run τ²-bench (airline 50, retail 114, telecom 114) for an Agent-Reflex checkpoint.
---

# τ²-bench

- **Setup**: `bash Tau2/setup.sh` clones tau2-bench at `672227c`, applies
  `tau2_agent_reflex.patch` (judge models and HTTP pool size configurable
  from the environment) and links the shipped `data/tau2` as the data dir.
- **Run**: `RUN_NAME=<name> bash Tau2/run.sh`. Smoke: `TAU2_NUM_TASKS=5`.
  One domain: `TAU2_DOMAINS=retail`.
- **Protocol**: base split, 1 trial, seed 300, agent temperature 0.0, user
  `gpt-4.1` at temperature 0.0, NL-assertion judge `gpt-4.1`, 120 concurrent
  tasks.
- **Score**: `summary.json` → micro-average reward × 100 over 278 tasks, plus
  per-domain values. `validate.py` checks the ids against `expected_ids.json`;
  a run with missing ids is reported, not silently averaged.
- **Pitfalls**: telecom tasks are long (up to 100+ turns); a 30-minute
  `LLM_READ_TIMEOUT` is set because thinking turns can take minutes under
  load. Re-running with the same `RUN_NAME` and `RUN_TAG` resumes.
