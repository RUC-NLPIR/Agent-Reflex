#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen/Qwen3-8B}"
TIMEOUT_SEC="${TIMEOUT_SEC:-900}"
export NO_PROXY=127.0.0.1,localhost
export no_proxy="$NO_PROXY"

deadline=$((SECONDS + TIMEOUT_SEC))
while (( SECONDS < deadline )); do
  if models_json="$(curl --noproxy '*' --max-time 5 -fsS "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null)"; then
    python3 - "$models_json" "$SERVED_MODEL_NAME" <<'PY'
import json, sys
models = {item["id"] for item in json.loads(sys.argv[1])["data"]}
expected = sys.argv[2]
if expected not in models:
    raise SystemExit(f"expected {expected!r}, got {sorted(models)!r}")
print("vllm_models=PASS", sorted(models))
PY
    exit 0
  fi
  sleep 5
done
echo "wait_vllm: timed out after ${TIMEOUT_SEC}s" >&2
exit 1
