#!/usr/bin/env bash
# ReSFT launcher. Works single-node and multi-node (torchrun via FORCE_TORCHRUN).
#
#   MODEL_PATH=/path/to/Qwen3-8B bash scripts/train_resft.sh [key=value ...]
#
# Extra key=value arguments override the YAML (LLaMA-Factory OmegaConf syntax).
# Multi-node: set NNODES / NODE_RANK / MASTER_ADDR / MASTER_PORT (Brain RJob
# exports NODE_COUNT and NODE_RANK; they are picked up automatically).
set -euo pipefail

LF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${LF_ROOT}"

: "${MODEL_PATH:?set MODEL_PATH to the base model (e.g. Qwen3-8B)}"
CONFIG="${CONFIG:-examples/agent_reflex/qwen3_8b_resft_32k.yaml}"
OUTPUT_DIR="${OUTPUT_DIR:-saves/qwen3-8b-agent-reflex-resft}"
ENV_DIR="${ENV_DIR:-${LF_ROOT}/.venv}"
[[ -x "${ENV_DIR}/bin/llamafactory-cli" ]] && export PATH="${ENV_DIR}/bin:${PATH}"

export NNODES="${NNODES:-${NODE_COUNT:-1}}"
export NODE_RANK="${NODE_RANK:-${RANK:-0}}"
export NPROC_PER_NODE="${NPROC_PER_NODE:-${PROC_PER_NODE:-$(nvidia-smi -L | wc -l)}}"
export MASTER_ADDR="${MASTER_ADDR:-127.0.0.1}"
export MASTER_PORT="${MASTER_PORT:-29501}"
export FORCE_TORCHRUN=1
export DISABLE_VERSION_CHECK=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export NCCL_DEBUG="${NCCL_DEBUG:-WARN}"
export PYTHONUNBUFFERED=1

mkdir -p "${OUTPUT_DIR}"
LOG="${OUTPUT_DIR}/training.log"
[[ "${NODE_RANK}" == "0" ]] || LOG="${OUTPUT_DIR}/training_node-${NODE_RANK}.log"

echo "[ReSFT] nodes=${NNODES} rank=${NODE_RANK} gpus/node=${NPROC_PER_NODE} config=${CONFIG}" | tee -a "${LOG}"
llamafactory-cli train "${CONFIG}" \
  model_name_or_path="${MODEL_PATH}" \
  output_dir="${OUTPUT_DIR}" \
  "$@" 2>&1 | tee -a "${LOG}"
