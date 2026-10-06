#!/usr/bin/env bash
# Build the ReSFT environment (Python 3.12, torch 2.6.0+cu124, flash-attn 2.7.4).
#
#   bash setup_env.sh                 # creates ./.venv
#   ENV_DIR=/path/to/env bash setup_env.sh
set -euo pipefail

LF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${ENV_DIR:-${LF_ROOT}/.venv}"
# The venv links to its interpreter; keep it next to the venv on shared storage
# so the environment also works on compute nodes.
export UV_MANAGED_PYTHON=1 UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$(dirname "${ENV_DIR}")/.uv-python}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"
FLASH_ATTN_WHEEL="${FLASH_ATTN_WHEEL:-https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl}"

command -v uv >/dev/null || { echo "uv not found: pip install uv" >&2; exit 2; }
uv venv --python 3.12 --seed "${ENV_DIR}"
PY="${ENV_DIR}/bin/python"

# The default PyPI build of torch 2.6.0 is the CUDA 12.4 one.
uv pip install --python "${PY}" torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0
uv pip install --python "${PY}" -r "${LF_ROOT}/requirements.txt"
uv pip install --python "${PY}" "${FLASH_ATTN_WHEEL}"
uv pip install --python "${PY}" --no-deps -e "${LF_ROOT}"

"${PY}" - <<'EOF'
# flash_attn / liger_kernel need a GPU driver to import; check installation only.
from importlib.metadata import version
import torch, transformers
print(f"torch={torch.__version__} cuda={torch.version.cuda} transformers={transformers.__version__}")
print(" ".join(f"{p}={version(p)}" for p in ("deepspeed", "flash-attn", "liger-kernel", "llamafactory")))
EOF
echo "ReSFT env ready: ${ENV_DIR}"
