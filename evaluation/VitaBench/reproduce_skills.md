---
name: reproduce-vitabench
description: Run VitaBench (delivery, instore, ota, cross-domain; 100 tasks each) for an Agent-Reflex checkpoint.
---

# VitaBench

- **Setup**: `bash VitaBench/setup.sh` clones vitabench at `742e240`, applies
  `vitabench_agent_reflex.patch` and links the shipped `data/vita/domains`.
  The patch only: reads gateway credentials from the environment, sends
  OpenAI-only fields to the gateway, retries a failed request (same model,
  `RETRY` times), answers the resume prompt non-interactively and sets the
  default judge to `claude-sonnet-4-6`.
- **Models**: `models.yaml` (no credentials; base URL and key are injected
  from `BOYUE_*`).
- **Run**: `RUN_NAME=<name> bash VitaBench/run.sh`.
  Smoke: `VITA_DOMAINS=delivery NUM_TASKS=5`. Domains are `+`-separated
  because the cross domain is itself `delivery,instore,ota`.
- **Protocol**: Chinese tasks, agent temperature 0.0, thinking on, user
  `gpt-4.1`, judge `claude-sonnet-4-6`, 300 max steps, 1 trial.
- **Score**: `summary.json` → trajectory pass@1 × 100. Upstream leaves crashed
  tasks out of `results.csv`; the summary counts them as 0 against the full
  100 per domain and lists them under `missing_tasks`. Re-run the same
  `RUN_NAME`/`RUN_TAG` to resume and fill them in.
