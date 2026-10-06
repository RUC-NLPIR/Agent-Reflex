#!/usr/bin/env bash
# ACEBench agent split through the EnvScaler interactive harness (code vendored in
# interact_with_env/, Apache-2.0, https://github.com/RUC-NLPIR/EnvScaler).
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

ENV_DIR="$RUNTIME/envscaler-env"
uv venv --python 3.10 --seed "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" -r "$BENCH/requirements.txt"
"$ENV_DIR/bin/python" -c 'import openai, pydantic, dotenv; print("ACEBench env ready")'
