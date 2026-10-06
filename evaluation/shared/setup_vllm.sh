#!/usr/bin/env bash
# vLLM serving environment used for every bench in the paper (vLLM 0.27.1, Python 3.12).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

ENV_DIR="${VLLM_ENV_DIR:-$RUNTIME/vllm-env}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"
uv venv --clear --python 3.12 --seed "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" -r "$(dirname "${BASH_SOURCE[0]}")/requirements-vllm.txt"
# Importing vllm needs a GPU; on a CPU build node only check the installation.
"$ENV_DIR/bin/python" -c "from importlib.metadata import version; print('vllm', version('vllm'))"
