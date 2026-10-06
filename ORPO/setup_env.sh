#!/usr/bin/env bash
# Create the ORPO training environment (Python 3.10, torch 2.7.1+cu128, SGLang 0.4.10.post2).
#
#   ENV_DIR=/path/to/orpo-env bash setup_env.sh
#
# Needs `uv` (https://docs.astral.sh/uv/) and an NVIDIA driver for CUDA 12.8.
# No CUDA toolkit is required: flash-attn comes from a prebuilt wheel.
set -euo pipefail

ORPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${ENV_DIR:-${ORPO_ROOT}/.venv}"
# The venv links to its interpreter; keep it next to the venv on shared storage
# so the environment also works on compute nodes.
export UV_MANAGED_PYTHON=1 UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$(dirname "${ENV_DIR}")/.uv-python}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
FLASH_ATTN_WHEEL="${FLASH_ATTN_WHEEL:-https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.7cxx11abiTRUE-cp310-cp310-linux_x86_64.whl}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"

command -v uv >/dev/null || { echo "uv not found: pip install uv" >&2; exit 2; }

uv venv --python 3.10 --seed "${ENV_DIR}"
PY="${ENV_DIR}/bin/python"

uv pip install --python "${PY}" torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
  --extra-index-url "${TORCH_INDEX_URL}" --index-strategy unsafe-best-match
uv pip install --python "${PY}" -r "${ORPO_ROOT}/requirements.txt"
uv pip install --python "${PY}" "${FLASH_ATTN_WHEEL}"
uv pip install --python "${PY}" --no-deps -e "${ORPO_ROOT}"

"${PY}" - <<'PY'
# flash_attn / sgl_kernel need a GPU driver to import; on a CPU-only login node
# only check that they are installed.
from importlib.metadata import version
import ray, torch, transformers, verl
print(f"torch={torch.__version__} cuda={torch.version.cuda} transformers={transformers.__version__} ray={ray.__version__}")
print(" ".join(f"{p}={version(p)}" for p in ("sglang", "sgl-kernel", "flash-attn")))
PY
echo "ORPO environment ready: export PYTHON_BIN=${PY}"
