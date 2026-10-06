#!/usr/bin/env bash
# ACEBench agent: multi-step 20 + multi-turn 30 = 50 tasks, EnvScaler protocol
# (native FC, thinking on, temperature 0.7, gpt-4.1 user, 20 truncated steps).
# Overall = (step_reward + turn_reward) / 50 x 100.
#
#   RUN_NAME=agent-reflex bash ACEBench/run.sh
#   ACE_NUM_STEP=2 ACE_NUM_TURN=2 RUN_NAME=smoke bash ACEBench/run.sh
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
require_boyue

PY="${ACE_PYTHON:-$RUNTIME/envscaler-env/bin/python}"
[[ -x "$PY" ]] || { echo "run ACEBench/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_DIR="$OUTPUT_ROOT/acebench/${RUN_NAME}-${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
N_STEP="${ACE_NUM_STEP:-20}"
N_TURN="${ACE_NUM_TURN:-30}"

export OPENAI_BASE_URL="$AGENT_BASE_URL" OPENAI_API_KEY=EMPTY
export VLLM_MAX_ATTEMPTS_PER_CLIENT="$RETRY"
mkdir -p "$RUN_DIR/results" "$RUN_DIR/validation"
exec > >(tee -a "$RUN_DIR/acebench.log") 2>&1

run_subset() { # env_name id_prefix count
  local env_name="$1" prefix="$2" n="$3"
  local ids; ids="$(python3 -c "print(','.join(f'$prefix{i}' for i in range($n)))")"
  assert_served_model
  (cd "$BENCH/interact_with_env" && "$PY" run_main.py \
    --env-name "$env_name" \
    --agent-model "$SERVED_MODEL_NAME" --agent-model-provider openai \
    --user-model "$USER_MODEL" --user-model-provider openai \
    --infer-mode fc --enable-thinking true \
    --temperature "${AGENT_TEMPERATURE:-0.7}" \
    --num-workers "$NUM_WORKERS" \
    --vllm-max-attempts-per-client "$RETRY" \
    --task-ids "$ids" \
    --save-file-path "$RUN_DIR/results/${env_name}.json")
  python3 "$BENCH/validate.py" "$RUN_DIR/results/${env_name}.json" \
    --expected-ids "prefix:${prefix}:${n}" \
    --summary "$RUN_DIR/validation/${env_name}.json" || true
}

run_subset acebench_multi_step agent_multi_step_ "$N_STEP"
run_subset acebench_multi_turn agent_multi_turn_ "$N_TURN"

python3 - "$RUN_DIR" <<'PY'
import json, sys
from pathlib import Path
run_dir = Path(sys.argv[1])
subsets = {n: json.loads((run_dir / "validation" / f"{n}.json").read_text())
           for n in ("acebench_multi_step", "acebench_multi_turn")
           if (run_dir / "validation" / f"{n}.json").exists()}
tasks = sum(s["actual_tasks"] for s in subsets.values())
reward = sum(s["reward_sum"] for s in subsets.values())
ok = len(subsets) == 2 and all(s["status"] == "PASS" for s in subsets.values()) and reward > 0
summary = {
    "status": "PASS" if ok else "FAIL",
    "overall": 100.0 * reward / tasks if tasks else None,
    "step": subsets.get("acebench_multi_step", {}).get("score"),
    "turn": subsets.get("acebench_multi_turn", {}).get("score"),
    "tasks": tasks,
}
(run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
sys.exit(0 if ok else 1)
PY
