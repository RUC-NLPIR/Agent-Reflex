#!/usr/bin/env bash
# Paper setting: Qwen3-8B policy, one 8-GPU node, 100 ORPO updates.
#   MODEL_PATH=/path/to/ReSFT-checkpoint bash scripts/run_orpo_qwen3_8b.sh
# Resume an interrupted run by appending trainer.resume_mode=auto.
set -euo pipefail
ORPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export EXP_NAME="${EXP_NAME:-orpo_qwen3_8b}"
export TOTAL_TRAINING_STEPS="${TOTAL_TRAINING_STEPS:-100}"
export TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-64}"
export ROLLOUT_N="${ROLLOUT_N:-8}"
export NOISE_ROLLOUT_FRACTION="${NOISE_ROLLOUT_FRACTION:-0.25}"
export NOISE_RATE="${NOISE_RATE:-0.2}"
export OPD_LOSS_COEF="${OPD_LOSS_COEF:-0.01}"
export OPD_GATE_BETA="${OPD_GATE_BETA:-5.0}"
export SAVE_FREQ="${SAVE_FREQ:-20}"
export TEST_FREQ="${TEST_FREQ:-10}"

exec bash "${ORPO_ROOT}/scripts/train_orpo.sh" "$@"
