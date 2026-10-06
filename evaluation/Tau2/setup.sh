#!/usr/bin/env bash
# Official tau2-bench code at a pinned commit, plus two harness-only patches (no
# scoring change):
#   * the NL-assertion judge / env-interface model names can be set by env var
#     (the gateway publishes gpt-4.1-2025-04-14 under the alias `gpt-4.1`)
#   * a larger LiteLLM connection pool, so 120 concurrent tasks are not throttled locally
# Task data ships in Tau2/data (airline, retail, telecom text domains of the same commit).
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

COMMIT=672227c6b6676edc20d57ea53b7000262aae77b9
SRC="$RUNTIME/tau2-bench"
ENV_DIR="$RUNTIME/tau2-env"

[[ -d "$SRC/.git" ]] || git clone --filter=blob:none https://github.com/sierra-research/tau2-bench.git "$SRC"
git -C "$SRC" checkout -q --force "$COMMIT"
git -C "$SRC" apply "$BENCH/tau2_agent_reflex.patch"

# TAU2_DATA_DIR = shipped domains + a writable simulations/ directory.
mkdir -p "$RUNTIME/tau2-data"
ln -sfn "$BENCH/data/tau2" "$RUNTIME/tau2-data/tau2"

uv venv --python 3.12 --seed "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" -r "$BENCH/requirements.txt"
uv pip install --python "$ENV_DIR/bin/python" --no-deps -e "$SRC"
"$ENV_DIR/bin/python" -c 'import tau2, litellm; print("tau2 ready")'
