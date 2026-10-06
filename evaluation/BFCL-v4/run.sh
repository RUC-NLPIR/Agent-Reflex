#!/usr/bin/env bash
# BFCL V4 all_scoring (5217 cases) against the local vLLM (registry local-qwen3-8b-FC).
#   Overall = 10% Non-Live + 10% Live + 10% Irrelevance + 30% Multi-Turn + 40% Agentic
#   Agentic = (Web Search + Memory) / 2
#
# Serve with shared/serve_vllm.sh first. Then:
#   RUN_NAME=agent-reflex bash BFCL-v4/run.sh
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

PKG="$BENCH/runner"
PY="$PKG/.venv/bin/python"
[[ -x "$PY" ]] || { echo "run BFCL-v4/setup.sh first" >&2; exit 2; }
RUN_NAME="${RUN_NAME:?RUN_NAME is required}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${RUN_NAME}}"
SUITE="${BFCL_SUITE:-all}"
REGISTRY=local-qwen3-8b-FC
RESULT_DIR="$PKG/runs/$RUN_ID/project-root/result/$REGISTRY"
OUT="$OUTPUT_ROOT/bfcl-v4/$RUN_ID"

export LOCAL_VLLM_BASE_URL="$AGENT_BASE_URL" LOCAL_VLLM_REQUEST_MODEL="$SERVED_MODEL_NAME"
export LOCAL_VLLM_MAX_TOTAL_TOKENS="${MAX_MODEL_LEN:-40960}"
export BFCL_SEARCH_PROVIDER=serper SERPER_REQUEST_TIMEOUT=120
export BOYUE_MAX_SEND_ATTEMPTS="$RETRY" BOYUE_REQUEST_TIMEOUT="$LLM_READ_TIMEOUT"
export PYTHONPATH="$PKG/adapter${PYTHONPATH:+:$PYTHONPATH}"
[[ "$SUITE" == all && -z "$SERPER_API_KEY" ]] && { echo "SERPER_API_KEY is required for the web-search category" >&2; exit 2; }

mkdir -p "$OUT"
exec > >(tee -a "$OUT/bfcl-v4.log") 2>&1
assert_served_model

cd "$PKG"
echo "BFCL-v4 run_id=$RUN_ID suite=$SUITE workers=$NUM_WORKERS"
RUN_ID="$RUN_ID" MODEL=qwen3-8b-local SUITE="$SUITE" WORKERS="$NUM_WORKERS" \
  bash scripts/run_eval.sh || echo "generate exited non-zero; repairing" >&2

# Transport failures leave "Error during inference" placeholders, which official
# scoring counts as wrong. Regenerate exactly those ids before scoring.
export BFCL_PROJECT_ROOT="$PKG/runs/$RUN_ID/project-root"
export BFCL_BOYUE_TRACE_ROOT="$PKG/runs/$RUN_ID/raw-api" BFCL_SEARCH_TRACE_ROOT="$PKG/runs/$RUN_ID/search-trace"
IDS_FILE="$BFCL_PROJECT_ROOT/test_case_ids_to_generate.json"
for attempt in 1 2 3; do
  "$PY" scripts/sanitize_result_jsonl.py --result-dir "$RESULT_DIR" || true
  n="$("$PY" scripts/prepare_repairs.py --result-dir "$RESULT_DIR" --output "$IDS_FILE")"
  (( n == 0 )) && break
  echo "repair $attempt: $n placeholders"
  "$PY" -m bfcl_boyue generate --model "$REGISTRY" --run-ids --allow-overwrite \
    --skip-server-setup --include-input-log --num-threads "$NUM_WORKERS" \
    ${BFCL_TEMPERATURE:+--temperature "$BFCL_TEMPERATURE"} || true
done

category="$("$PY" -c "from bfcl_boyue.app import SUITES; print(','.join(SUITES['$SUITE']))")"
"$PY" -m bfcl_boyue evaluate --model "$REGISTRY" --test-category "$category"
cp "$BFCL_PROJECT_ROOT"/score/data_*.csv "$OUT/" 2>/dev/null || true
"$PY" scripts/validate_run.py "$RUN_ID" --root "$PKG" --summary "$OUT/validation.json" --max-placeholders 200 || true
echo "scores: $OUT/data_overall.csv"
