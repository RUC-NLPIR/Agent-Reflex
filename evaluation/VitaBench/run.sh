#!/usr/bin/env bash
# VitaBench: delivery / instore / ota / cross-domain, 100 tasks each, trajectory pass@1.
#
#   RUN_NAME=agent-reflex bash VitaBench/run.sh
#   VITA_DOMAINS=delivery NUM_TASKS=3 RUN_NAME=smoke bash VitaBench/run.sh
#
# VITA_DOMAINS is '+'-separated because the cross domain itself is "delivery,instore,ota".
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
require_boyue

VITA="$RUNTIME/vita-env/bin/vita"
[[ -x "$VITA" ]] || { echo "run VitaBench/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$OUTPUT_ROOT/vitabench/${RUN_NAME}-${RUN_TAG}"
DOMAINS="${VITA_DOMAINS:-delivery+instore+ota+delivery,instore,ota}"

export VITA_MODEL_CONFIG_PATH="${VITA_MODEL_CONFIG_PATH:-$BENCH/models.yaml}"
export VITA_AUTO_RESUME=1
export VITA_LLM_TIMEOUT="$LLM_READ_TIMEOUT"
export VITA_LLM_MAX_RETRIES="$RETRY"
mkdir -p "$RUN_DIR"
exec > >(tee -a "$RUN_DIR/vitabench.log") 2>&1
assert_served_model

cd "$RUNTIME/vitabench"
IFS='+' read -r -a DOMAIN_LIST <<<"$DOMAINS"
for domain in "${DOMAIN_LIST[@]}"; do
  echo "=== Vita domain=$domain ==="
  args=(run --domain "$domain"
    --agent-llm "$SERVED_MODEL_NAME" --enable-think
    --user-llm "$USER_MODEL" --evaluator-llm "$VITA_EVALUATOR_MODEL"
    --num-trials 1 --max-steps 300 --language chinese
    --max-concurrency "$NUM_WORKERS"
    --save-to "${RUN_NAME}-${domain//,/-}-${RUN_TAG}.json"
    --csv-output "$RUN_DIR/results.csv")
  [[ -n "${NUM_TASKS:-}" ]] && args+=(--num-tasks "$NUM_TASKS")
  "$VITA" "${args[@]}"
done

# Upstream leaves crashed tasks out of results.csv; score them as 0 against the
# full per-domain count (100, or NUM_TASKS) and report how many are missing.
python3 - "$RUN_DIR" "${NUM_TASKS:-100}" <<'PY'
import csv, json, sys
from pathlib import Path
run_dir, expected = Path(sys.argv[1]), int(sys.argv[2])
rows = {r["domain"]: r for r in csv.DictReader(open(run_dir / "results.csv"))}
passed = {d: float(r["trajectory_pass_at_1"]) * int(r["num_tasks"]) for d, r in rows.items()}
summary = {
    "status": "PASS" if rows and sum(passed.values()) > 0 else "FAIL",
    "overall": 100.0 * sum(passed.values()) / (expected * len(rows)) if rows else None,
    **{d: 100.0 * p / expected for d, p in passed.items()},
    "missing_tasks": {d: expected - int(r["num_tasks"]) for d, r in rows.items() if int(r["num_tasks"]) < expected},
}
(run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
sys.exit(0 if summary["status"] == "PASS" else 1)
PY
