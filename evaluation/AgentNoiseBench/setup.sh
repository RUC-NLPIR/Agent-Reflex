#!/usr/bin/env bash
# AgentNoiseBench: noise-injecting forks of tau2-bench and VitaBench (source in repo/).
# Task data is shipped: tau2 in AgentNoiseBench/data, Vita reuses VitaBench/data.
# Noise is generated online by gpt-4.1 on the Boyue gateway.
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

ENV_DIR="$RUNTIME/agentnoise-env"
DATA="$RUNTIME/agentnoise"

# Both forks resolve data as <DATA_DIR>/<bench>/domains/...
mkdir -p "$DATA/tau2-data" "$DATA/vita-data/vita"
ln -sfn "$BENCH/data/tau2" "$DATA/tau2-data/tau2"
ln -sfn "$BENCH/../VitaBench/data/vita/domains" "$DATA/vita-data/vita/domains"
ln -sfn "$DATA/vita-data" "$BENCH/repo/vitabench/data"

uv venv --python 3.12 --seed "$ENV_DIR"
# Pinned to the versions the forks were developed with; unpinned, the resolver
# backtracks through hundreds of litellm releases against httpx<0.28.
uv pip install --python "$ENV_DIR/bin/python" \
  -e "$BENCH/repo/vitabench" -e "$BENCH/repo/tau2-bench-main" \
  'httpx==0.27.2' 'litellm==1.72.2' 'openai==1.109.1' json-repair python-dotenv tenacity
"$ENV_DIR/bin/vita" --help >/dev/null && "$ENV_DIR/bin/tau2" --help >/dev/null && echo "AgentNoiseBench ready"
