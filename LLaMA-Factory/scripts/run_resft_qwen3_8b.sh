#!/usr/bin/env bash
# Paper ReSFT run: Qwen3-8B, 2 nodes x 8 GPUs, global batch 32, 3 epochs (5127 steps).
# Launch the same command on every node (NNODES=2, NODE_RANK=0/1, shared MASTER_ADDR).
set -euo pipefail
export NNODES="${NNODES:-${NODE_COUNT:-2}}"
exec bash "$(dirname "${BASH_SOURCE[0]}")/train_resft.sh" "$@"
