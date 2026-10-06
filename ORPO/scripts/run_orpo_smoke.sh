#!/usr/bin/env bash
# Two ORPO updates on 8 GPUs to check that the stack runs end to end:
# rollout with fault injection, skill re-scoring, GRPO + OPD update.
# No validation and no checkpoint, so it finishes in well under an hour.
set -euo pipefail
ORPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export EXP_NAME="${EXP_NAME:-orpo_smoke}"
export TOTAL_TRAINING_STEPS="${TOTAL_TRAINING_STEPS:-2}"
export TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-8}"
export ROLLOUT_N="${ROLLOUT_N:-8}"
export MAX_ASSISTANT_TURNS="${MAX_ASSISTANT_TURNS:-20}"
export MAX_RESPONSE_LENGTH="${MAX_RESPONSE_LENGTH:-8192}"
export SAVE_FREQ=-1
export TEST_FREQ=-1
export VAL_BEFORE_TRAIN=False

exec bash "${ORPO_ROOT}/scripts/run_orpo_qwen3_8b.sh" "$@"
