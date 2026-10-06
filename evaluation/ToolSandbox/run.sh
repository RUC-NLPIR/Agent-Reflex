#!/usr/bin/env bash
# ToolSandbox: first 200 offline scenarios (no RapidAPI tools), mean similarity.
#
#   RUN_NAME=agent-reflex bash ToolSandbox/run.sh
#   TOOLSANDBOX_N=5 RUN_NAME=smoke bash ToolSandbox/run.sh
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
require_boyue

ENV_DIR="$RUNTIME/toolsandbox-env"
[[ -x "$ENV_DIR/bin/tool_sandbox" ]] || { echo "run ToolSandbox/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_DIR="$OUTPUT_ROOT/toolsandbox/${RUN_NAME}-${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
N="${TOOLSANDBOX_N:-200}"

export TOOL_SANDBOX_AGENT_BASE_URL="$AGENT_BASE_URL"
export TOOL_SANDBOX_AGENT_MODEL="$SERVED_MODEL_NAME"
export TOOL_SANDBOX_AGENT_API_KEY=EMPTY
export TOOL_SANDBOX_AGENT_TIMEOUT="$LLM_READ_TIMEOUT"
export TOOL_SANDBOX_AGENT_MAX_RETRIES="$RETRY"
export TOOL_SANDBOX_AGENT_MAX_TOKENS="${TOOL_SANDBOX_AGENT_MAX_TOKENS:-8192}"
export TOOL_SANDBOX_AGENT_TEMPERATURE="${AGENT_TEMPERATURE:-0.6}"
export TOOL_SANDBOX_AGENT_TOP_P="${AGENT_TOP_P:-0.95}"
export TOOL_SANDBOX_AGENT_TOP_K="${AGENT_TOP_K:-20}"
export TOOL_SANDBOX_USER_MODEL="$USER_MODEL"
export TOOL_SANDBOX_USER_API_KEY="$USER_OPENAI_API_KEY"
export TOOL_SANDBOX_USER_BASE_URL="$USER_OPENAI_BASE_URL"
export TOOL_SANDBOX_USER_TIMEOUT=600
export TOOL_SANDBOX_USER_MAX_RETRIES="$RETRY"

mkdir -p "$RUN_DIR"
exec > >(tee -a "$RUN_DIR/toolsandbox.log") 2>&1
assert_served_model

cd "$RUNTIME/ToolSandbox"
mapfile -t SCENARIOS < <("$ENV_DIR/bin/python" "$BENCH/list_offline_scenarios.py" "$N")
run_ts() { # output_dir scenarios...
  local out="$1"; shift
  "$ENV_DIR/bin/tool_sandbox" --agent Qwen3_8B --user GPT_4_1 \
    --parallel "$NUM_WORKERS" --output_dir "$out" --scenarios "$@"
}
run_ts "$RUN_DIR/main" "${SCENARIOS[@]}"

SUMMARY="$(find "$RUN_DIR/main" -name result_summary.json | head -1)"
[[ -n "$SUMMARY" ]] || { echo "ToolSandbox produced no result_summary.json" >&2; exit 1; }

# Re-run scenarios that crashed on infrastructure errors, then merge them back.
for attempt in $(seq 1 3); do
  mapfile -t FAILED < <("$ENV_DIR/bin/python" "$BENCH/repair.py" --summary "$SUMMARY" | sed '1d')
  (( ${#FAILED[@]} == 0 )) && break
  echo "repair $attempt: ${#FAILED[@]} scenarios"
  run_ts "$RUN_DIR/repair-$attempt" "${FAILED[@]}"
  patch="$(find "$RUN_DIR/repair-$attempt" -name result_summary.json | head -1)"
  [[ -n "$patch" ]] && "$ENV_DIR/bin/python" "$BENCH/repair.py" --summary "$SUMMARY" --merge-from "$patch" --write
done

python3 - "$SUMMARY" "$RUN_DIR/summary.json" "$N" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))["per_scenario_results"]
avg = 100.0 * sum(r["similarity"] for r in rows) / len(rows)
exc = sum(1 for r in rows if r.get("traceback")) / len(rows)
ok = len(rows) == int(sys.argv[3]) and exc == 0 and avg > 0
summary = {"status": "PASS" if ok else "FAIL", "similarity": avg, "n": len(rows), "exception_rate": exc}
open(sys.argv[2], "w").write(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
sys.exit(0 if ok else 1)
PY
