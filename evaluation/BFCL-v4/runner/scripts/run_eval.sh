#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODEL="${MODEL:-qwen3-8b-local}"
SUITE="${SUITE:-all}"
WORKERS="${WORKERS:-${BFCL_WORKERS:-120}}"
RUN_ID="${RUN_ID:-}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen/Qwen3-8B}"
PORT="${PORT:-8000}"

# The local vLLM must never go through a proxy; set HTTP(S)_PROXY yourself if
# the user simulator / Serper need one.
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "run_eval: environment missing; run ./bfcl setup first" >&2
  exit 2
fi

bash "$ROOT/scripts/wait_vllm.sh"
bash "$ROOT/scripts/smoke_vllm.sh"

args=(run --model "$MODEL" --suite "$SUITE" --workers "$WORKERS")
if [[ -n "$RUN_ID" ]]; then
  args+=(--run-id "$RUN_ID")
fi

echo "run_eval: ./bfcl ${args[*]}"
exec "$ROOT/bfcl" "${args[@]}"
