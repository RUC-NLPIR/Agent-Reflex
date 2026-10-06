#!/usr/bin/env bash
# AgentNoiseBench on tau2 (airline/retail/telecom) and Vita (delivery/instore/ota).
#
# Two settings, as in the paper (not a cartesian product):
#   Tool noise : user=original  x tool in {fault, incomplete, induce, redundant, wrong}
#   User noise : tool=others    x user in {ambiguity, topic_shift, conflict, redundancy, boundary}
#                                 (+ cognition for tau2)
#   Clean      : tool=others, user=original
#
#   RUN_NAME=agent-reflex bash AgentNoiseBench/run.sh            # everything
#   MODE=tau2 RUN_NAME=agent-reflex bash AgentNoiseBench/run.sh  # tau2 | vita | smoke
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
require_boyue

ENV_DIR="$RUNTIME/agentnoise-env"
[[ -x "$ENV_DIR/bin/vita" ]] || { echo "run AgentNoiseBench/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
MODE="${MODE:-all}"
RUN_DIR="$OUTPUT_ROOT/agentnoisebench/${RUN_NAME}-${RUN_TAG}"

TOOL_NOISES=(fault incomplete induce redundant wrong)
VITA_USER_NOISES=(ambiguity topic_shift conflict redundancy boundary)
TAU2_USER_NOISES=(ambiguity topic_shift conflict redundancy boundary cognition)
read -r -a TAU2_DOMAINS <<<"${TAU2_DOMAINS:-airline retail telecom}"
read -r -a VITA_DOMAINS <<<"${VITA_DOMAINS:-delivery instore ota}"

export TAU2_DATA_DIR="$RUNTIME/agentnoise/tau2-data"
export VITA_MODEL_CONFIG_PATH="$BENCH/../VitaBench/models.yaml"
export TAU2_MODEL_CONFIG_PATH="$VITA_MODEL_CONFIG_PATH"
export VITA_AUTO_RESUME=1 TAU2_AUTO_RESUME=1
export VITA_LLM_TIMEOUT="$LLM_READ_TIMEOUT" TAU2_LLM_TIMEOUT="$LLM_READ_TIMEOUT"

# Credentials for the noise generator / deviation auditor, written 0600 per run.
mkdir -p "$RUN_DIR"
export NOISE_ENV_PATH="$RUN_DIR/noise.env"
( umask 077; printf 'API_KEY=%s\nBASE_URL=%s\nMODEL=gpt-4.1\nEVAL=gpt-4.1\n' \
    "$BOYUE_API_KEY" "$BOYUE_API_BASE_URL" >"$NOISE_ENV_PATH" )
exec > >(tee -a "$RUN_DIR/agentnoise.log") 2>&1
assert_served_model

max_single_tool_noise() {
  case "$1" in wrong) echo 2 ;; induce|redundant|incomplete) echo 10 ;; *) echo 1 ;; esac
}

run_cell() { # bench domain tool user
  local bench="$1" domain="$2" tool="$3" user="$4"
  local save="${RUN_NAME}-${domain}-${tool}-${user}-${RUN_TAG}"
  local common=(--domain "$domain" --agent-llm "$SERVED_MODEL_NAME" --user-llm "$USER_MODEL"
    --enable-think --num-trials 1 --max-concurrency "$NUM_WORKERS"
    --noise_category "$tool" --priority_level 5 --noise_nums 100000
    --max_single_tool_noise "$(max_single_tool_noise "$tool")")
  [[ -n "${NUM_TASKS:-}" ]] && common+=(--num-tasks "$NUM_TASKS")
  echo "=== $bench domain=$domain tool=$tool user=$user $(date -Is) ==="
  assert_served_model
  if [[ "$bench" == vita ]]; then
    (cd "$BENCH/repo/vitabench" && "$ENV_DIR/bin/vita" run "${common[@]}" \
      --evaluator-llm "$VITA_EVALUATOR_MODEL" --max-steps 300 --language chinese \
      --user_noise "$user" --save-to "$save.json") || echo "cell failed: $save" >&2
  else
    (cd "$BENCH/repo/tau2-bench-main" && "$ENV_DIR/bin/tau2" run "${common[@]}" \
      --user-noise "$user" --save-to "$save") || echo "cell failed: $save" >&2
  fi
}

run_bench() { # bench
  local bench="$1" d t u users domains
  if [[ "$bench" == vita ]]; then domains=("${VITA_DOMAINS[@]}"); users=("${VITA_USER_NOISES[@]}")
  else domains=("${TAU2_DOMAINS[@]}"); users=("${TAU2_USER_NOISES[@]}"); fi
  for d in "${domains[@]}"; do
    run_cell "$bench" "$d" others original
    for t in "${TOOL_NOISES[@]}"; do run_cell "$bench" "$d" "$t" original; done
    for u in "${users[@]}"; do run_cell "$bench" "$d" others "$u"; done
  done
}

case "$MODE" in
  all)   run_bench tau2; run_bench vita ;;
  tau2)  run_bench tau2 ;;
  vita)  run_bench vita ;;
  smoke) NUM_TASKS="${NUM_TASKS:-2}"
         run_cell tau2 airline others original; run_cell tau2 airline fault original
         run_cell tau2 airline others ambiguity; run_cell vita delivery others original ;;
  *) echo "MODE must be all | tau2 | vita | smoke" >&2; exit 2 ;;
esac

"$ENV_DIR/bin/python" "$BENCH/summarize.py" --bench-root "$BENCH" \
  --tau2-data "$TAU2_DATA_DIR" --prefix "$RUN_NAME" --run-tag "$RUN_TAG" \
  --output "$RUN_DIR/summary.json"
