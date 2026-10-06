# Shared paths, credentials and protocol settings. Sourced by every bench entry.
#
# Credentials live in ONE file: evaluation/.env (copy from .env.example), or any
# file pointed to by ENV_FILE.
#   BOYUE_API_KEY / BOYUE_API_BASE_URL  -> user simulators, judges, noise generator
#   SERPER_API_KEY                      -> BFCL-v4 web search only

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${RUNTIME:-$EVAL_ROOT/.runtime}"          # venvs + upstream code checkouts
OUTPUT_ROOT="${OUTPUT_ROOT:-$EVAL_ROOT/outputs}"   # every bench writes under here
ENV_FILE="${ENV_FILE:-$EVAL_ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# One OpenAI-compatible gateway serves every external model. Each harness reads
# it under a different variable name, so fan it out once here.
BOYUE_API_KEY="${BOYUE_API_KEY:-}"
BOYUE_API_BASE_URL="${BOYUE_API_BASE_URL:-}"
BOYUE_API_BASE_URL="${BOYUE_API_BASE_URL%/}"
[[ -n "$BOYUE_API_BASE_URL" && "$BOYUE_API_BASE_URL" != */v1 ]] && BOYUE_API_BASE_URL="$BOYUE_API_BASE_URL/v1"
export BOYUE_API_KEY BOYUE_API_BASE_URL SERPER_API_KEY="${SERPER_API_KEY:-}"
export USER_OPENAI_API_KEY="$BOYUE_API_KEY" USER_OPENAI_BASE_URL="$BOYUE_API_BASE_URL"
export VITA_EXTERNAL_API_KEY="$BOYUE_API_KEY" VITA_EXTERNAL_BASE_URL="$BOYUE_API_BASE_URL"

# Model under test: the local vLLM started by shared/serve_vllm.sh.
export SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen/Qwen3-8B}"
export PORT="${PORT:-8000}"
export AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:${PORT}/v1}"
export CHAT_TEMPLATE_PATH="${CHAT_TEMPLATE_PATH:-$EVAL_ROOT/shared/configs/qwen3_force_thinking_chat_template.jinja}"

# Paper protocol: 8x H200, vLLM TP=8, thinking on.
# `gpt-4.1` on the gateway resolves to the official gpt-4.1-2025-04-14 snapshot.
export NUM_WORKERS="${NUM_WORKERS:-120}"
export RETRY="${RETRY:-10}"
export USER_MODEL="${USER_MODEL:-gpt-4.1}"
export VITA_EVALUATOR_MODEL="${VITA_EVALUATOR_MODEL:-claude-sonnet-4-6}"
export LLM_READ_TIMEOUT="${LLM_READ_TIMEOUT:-1800}"   # a long thinking turn takes minutes

# venvs link to their interpreter; keep it on the same shared storage so the
# venvs also work on compute nodes that only mount this directory.
export UV_MANAGED_PYTHON=1 UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$RUNTIME/python}"

export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"
export PYTHONUNBUFFERED=1
mkdir -p "$RUNTIME" "$OUTPUT_ROOT"

require_boyue() {
  if [[ -z "$BOYUE_API_KEY" || -z "$BOYUE_API_BASE_URL" ]]; then
    echo "Set BOYUE_API_KEY and BOYUE_API_BASE_URL in $ENV_FILE (see .env.example)." >&2
    exit 2
  fi
}

# Every checkpoint is served under the same alias, so an answering port proves
# nothing. Compare /v1/models .root against MODEL_PATH when it is known.
assert_served_model() {
  local body
  body="$(curl --noproxy '*' --max-time 10 -fsS "$AGENT_BASE_URL/models")" || {
    echo "vLLM is not answering at $AGENT_BASE_URL; run shared/serve_vllm.sh first" >&2
    return 1
  }
  MODELS_JSON="$body" python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["MODELS_JSON"]).get("data", [])
names = {m.get("id") for m in data}
roots = {(m.get("root") or "").rstrip("/") for m in data}
if os.environ["SERVED_MODEL_NAME"] not in names:
    sys.exit(f"served names {sorted(names)} do not include {os.environ['SERVED_MODEL_NAME']}")
want = os.environ.get("MODEL_PATH", "").rstrip("/")
if want and want not in roots:
    sys.exit(f"endpoint serves {sorted(roots)}, expected {want}")
PY
}
