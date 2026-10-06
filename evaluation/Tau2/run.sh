#!/usr/bin/env bash
# tau2-bench base split: airline 50 + retail 114 + telecom 114 = 278 tasks.
# Overall = micro-average reward x 100. Agent temperature 0.0 (tau2 default), user gpt-4.1.
#
#   RUN_NAME=agent-reflex bash Tau2/run.sh
#   TAU2_NUM_TASKS=5 RUN_NAME=smoke bash Tau2/run.sh      # first 5 tasks of each domain
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
require_boyue

PY="$RUNTIME/tau2-env/bin/python"
[[ -x "$PY" ]] || { echo "run Tau2/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$OUTPUT_ROOT/tau2/${RUN_NAME}-${RUN_TAG}"
DOMAINS="${TAU2_DOMAINS:-airline,retail,telecom}"

export MAX_CONCURRENCY="$NUM_WORKERS"
export TAU2_DATA_DIR="$RUNTIME/tau2-data"
export TAU2_AGENT_API_BASE="$AGENT_BASE_URL"
export TAU2_LLM_NL_ASSERTIONS="$USER_MODEL" TAU2_LLM_ENV_INTERFACE="$USER_MODEL"
# The NL-assertion judge and env interface take no api_base/api_key arguments;
# litellm falls back to these for them.
export OPENAI_API_KEY="$USER_OPENAI_API_KEY" OPENAI_API_BASE="$USER_OPENAI_BASE_URL"
export TAU2_LLM_TIMEOUT="$LLM_READ_TIMEOUT"
export LITELLM_LOCAL_MODEL_COST_MAP=True

mkdir -p "$RUN_DIR/results" "$RUN_DIR/validation"
exec > >(tee -a "$RUN_DIR/tau2.log") 2>&1
assert_served_model

for domain in ${DOMAINS//,/ }; do
  save_to="${RUN_NAME}-${RUN_TAG}-${domain}"
  echo "=== Tau2 domain=$domain concurrency=$MAX_CONCURRENCY ==="
  "$PY" "$BENCH/run_domain.py" "$domain" "$save_to" || echo "domain $domain exited non-zero" >&2
  src="$TAU2_DATA_DIR/simulations/$save_to/results.json"
  [[ -f "$src" ]] || { echo "missing $src" >&2; continue; }
  cp "$src" "$RUN_DIR/results/tau2_${domain}.json"
  python3 - "$BENCH/expected_ids.json" "$domain" "$RUN_DIR/validation/expected_${domain}.json" "${TAU2_NUM_TASKS:-}" <<'PY'
import json, sys
ids = json.load(open(sys.argv[1]))[sys.argv[2]]
if sys.argv[4]:
    ids = ids[: int(sys.argv[4])]
json.dump({"ids": ids}, open(sys.argv[3], "w"))
PY
  python3 "$BENCH/validate.py" "$RUN_DIR/results/tau2_${domain}.json" \
    --expected-ids "$RUN_DIR/validation/expected_${domain}.json" \
    --summary "$RUN_DIR/validation/tau2_${domain}.json" || true
done

python3 - "$RUN_DIR" "$DOMAINS" <<'PY'
import json, sys
from pathlib import Path
run_dir, domains = Path(sys.argv[1]), [d for d in sys.argv[2].split(",") if d]
subsets = {}
for d in domains:
    p = run_dir / "validation" / f"tau2_{d}.json"
    subsets[d] = json.loads(p.read_text()) if p.exists() else None
done = [s for s in subsets.values() if s]
tasks = sum(s["actual_tasks"] for s in done)
reward = sum(s["reward_sum"] for s in done)
ok = len(done) == len(domains) and all(s["status"] == "PASS" for s in done) and reward > 0
summary = {
    "status": "PASS" if ok else "FAIL",
    "overall": 100.0 * reward / tasks if tasks else None,
    **{d: (s or {}).get("score") for d, s in subsets.items()},
    "tasks": tasks,
}
(run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
sys.exit(0 if ok else 1)
PY
