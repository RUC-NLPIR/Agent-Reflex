---
name: reproduce-agentnoisebench
description: Run AgentNoiseBench (tool and user noise on τ²-bench and VitaBench) for an Agent-Reflex checkpoint.
---

# AgentNoiseBench

- **Code**: `repo/tau2-bench-main` and `repo/vitabench` are the
  AgentNoiseBench forks that inject noise online (generator `gpt-4.1`).
  Credentials are written per run to a 0600 `noise.env` in the run directory.
- **Data**: τ²-bench snapshot in `data/tau2/` (the version the fork was
  built against); VitaBench reuses `../VitaBench/data`.
- **Setup**: `bash AgentNoiseBench/setup.sh`.
- **Run**: `RUN_NAME=<name> bash AgentNoiseBench/run.sh`
  (`MODE=tau2|vita|smoke`; smoke = 4 cells: Tau2 airline clean, tool `fault`, user `ambiguity`, and
  Vita delivery clean, each on `NUM_TASKS` tasks, default 2).
- **Matrix** (not a cartesian product): per domain, one clean cell
  (tool `others`, user `original`), five tool-noise cells
  (fault, incomplete, induce, redundant, wrong; user `original`) and the
  user-noise cells (ambiguity, topic_shift, conflict, redundancy, boundary,
  plus cognition on τ²-bench; tools `others`). Domains: airline, retail,
  telecom / delivery, instore, ota.
- **Score**: `summarize.py` → Clean, Tool, User per bench, Avg = (Tool + User) / 2,
  Overall = mean of the τ²-bench and VitaBench Avg.
- **Settings**: concurrency `NUM_WORKERS` (120), priority level 5, judge as
  in VitaBench. The fork's optional per-task deadline (`TASK_TIMEOUT_SECONDS`)
  and user-simulator cap (`USER_LLM_CONCURRENCY`) are off unless you set them.
