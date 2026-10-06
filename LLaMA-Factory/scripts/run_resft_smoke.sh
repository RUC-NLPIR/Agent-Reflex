#!/usr/bin/env bash
# Single-node smoke test: same recipe, 256 samples, 5 optimizer steps, no checkpoint.
set -euo pipefail
export NNODES=1 NODE_RANK=0
export OUTPUT_DIR="${OUTPUT_DIR:-saves/resft-smoke}"
exec bash "$(dirname "${BASH_SOURCE[0]}")/train_resft.sh" \
  max_samples=256 max_steps=5 logging_steps=1 "save_strategy='no'" \
  preprocessing_num_workers=8 overwrite_output_dir=true "$@"
