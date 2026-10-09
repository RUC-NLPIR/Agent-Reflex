#!/usr/bin/env bash
# ORPO: noisy agentic RL (mixed clean / perturbed GRPO group) + reflection OPD.
#
# Every knob is an environment variable; the defaults reproduce the paper run
# (Qwen3-8B, 8 GPUs, 100 updates). Extra Hydra overrides can be appended:
#   bash scripts/train_orpo.sh trainer.resume_mode=auto
set -euo pipefail

ORPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ORPO_ROOT}"

if [[ -f "${ORPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ORPO_ROOT}/.env"
  set +a
fi

: "${MODEL_PATH:?Set MODEL_PATH to the policy initialization (Qwen3-8B or a ReSFT checkpoint)}"

# ============================ Paths ============================
PYTHON_BIN="${PYTHON_BIN:-python3}"
TRAIN_FILE="${TRAIN_FILE:-${ORPO_ROOT}/data/train_envscaler_2550_with_skills.jsonl}"
VAL_FILE="${VAL_FILE:-${ORPO_ROOT}/data/bfcl_val_128.jsonl}"
PROJECT_NAME="${PROJECT_NAME:-agent_reflex_orpo}"
EXP_NAME="${EXP_NAME:-orpo_qwen3_8b}"
CKPT_DIR="${CKPT_DIR:-${ORPO_ROOT}/checkpoints/${EXP_NAME}}"

# ============================ Cluster ============================
N_GPUS_PER_NODE="${N_GPUS_PER_NODE:-8}"
N_NODES="${N_NODES:-1}"
TP_SIZE="${TP_SIZE:-4}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.45}"
NUM_AGENT_WORKERS="${NUM_AGENT_WORKERS:-16}"

# ============================ Batch / length ============================
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-64}"
PPO_MINI_BATCH_SIZE="${PPO_MINI_BATCH_SIZE:-${TRAIN_BATCH_SIZE}}"
PPO_MICRO_BATCH_PER_GPU="${PPO_MICRO_BATCH_PER_GPU:-1}"
ROLLOUT_N="${ROLLOUT_N:-8}"
MAX_PROMPT_LENGTH="${MAX_PROMPT_LENGTH:-8192}"
MAX_RESPONSE_LENGTH="${MAX_RESPONSE_LENGTH:-16384}"
MAX_ASSISTANT_TURNS="${MAX_ASSISTANT_TURNS:-40}"
MAX_TOKENS_PER_STEP="${MAX_TOKENS_PER_STEP:-4096}"
MAX_TOOL_RESPONSE_LENGTH="${MAX_TOOL_RESPONSE_LENGTH:-1024}"
ROLLOUT_TEMPERATURE="${ROLLOUT_TEMPERATURE:-0.99}"
ROLLOUT_TOP_P="${ROLLOUT_TOP_P:-0.99}"

# ============================ Optimization ============================
ADV_ESTIMATOR="${ADV_ESTIMATOR:-grpo}"
ACTOR_LR="${ACTOR_LR:-1e-6}"
KL_COEF="${KL_COEF:-0.01}"
TOTAL_EPOCHS="${TOTAL_EPOCHS:-3}"
TOTAL_TRAINING_STEPS="${TOTAL_TRAINING_STEPS:-100}"
SAVE_FREQ="${SAVE_FREQ:-20}"
TEST_FREQ="${TEST_FREQ:-10}"
VAL_BEFORE_TRAIN="${VAL_BEFORE_TRAIN:-True}"

# ============================ ORPO ============================
# Reflection OPD: lambda_opd and the SEED confidence-weight temperature beta_opd.
# OPD_LOSS_COEF=0 disables OPD; OPD_GATE_BETA<=0 drops the confidence weight (OPSD).
OPD_LOSS_COEF="${OPD_LOSS_COEF:-0.01}"
OPD_GATE_BETA="${OPD_GATE_BETA:-5.0}"
# Noisy agentic RL: fraction nu of each group rolled out with per-tool-call faults.
# NOISE_ROLLOUT_FRACTION=0 gives clean-only rollouts.
NOISE_ROLLOUT_FRACTION="${NOISE_ROLLOUT_FRACTION:-0.25}"
NOISE_RATE="${NOISE_RATE:-0.2}"
# False = normalize the advantage over the whole mixed group (paper setting).
NOISE_ADV_SPLIT="${NOISE_ADV_SPLIT:-False}"
# Optional weighted fault catalog; empty = uniform over the eight fault families.
NOISE_CATALOG_PATH="${NOISE_CATALOG_PATH:-}"

# ============================ Memory ============================
ACTOR_PARAM_OFFLOAD="${ACTOR_PARAM_OFFLOAD:-True}"
ACTOR_OPTIMIZER_OFFLOAD="${ACTOR_OPTIMIZER_OFFLOAD:-True}"
REF_PARAM_OFFLOAD="${REF_PARAM_OFFLOAD:-True}"
FREE_CACHE_ENGINE="${FREE_CACHE_ENGINE:-True}"
LOGGER="${LOGGER:-[console]}"

case "${ADV_ESTIMATOR}" in
  grpo) ADV_ARGS=(algorithm.adv_estimator=grpo algorithm.norm_adv_by_std_in_grpo=True) ;;
  reinforce_plus_plus) ADV_ARGS=(algorithm.adv_estimator=reinforce_plus_plus algorithm.gamma=1.0) ;;
  *) echo "Unsupported ADV_ESTIMATOR=${ADV_ESTIMATOR} (grpo | reinforce_plus_plus)" >&2; exit 2 ;;
esac

EXTRA_ARGS=()
if [[ -n "${NOISE_CATALOG_PATH}" ]]; then
  EXTRA_ARGS+=("+actor_rollout_ref.rollout.multi_turn.noise_catalog_path=${NOISE_CATALOG_PATH}")
fi
if [[ -n "${ENABLE_THINKING:-}" ]]; then
  case "${ENABLE_THINKING}" in
    1) EXTRA_ARGS+=('+data.apply_chat_template_kwargs={enable_thinking: true}') ;;
    0) EXTRA_ARGS+=('+data.apply_chat_template_kwargs={enable_thinking: false}') ;;
    *) echo "ENABLE_THINKING must be 0, 1, or unset" >&2; exit 2 ;;
  esac
fi

for f in "${TRAIN_FILE}" "${VAL_FILE}"; do
  [[ -f "${f}" ]] || { echo "Missing data file: ${f}" >&2; exit 2; }
done

export PYTHONPATH="${ORPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONUNBUFFERED=1
export HYDRA_FULL_ERROR=1
# SGLang re-executes the interpreter for its scheduler processes; those must
# resolve the CUDA runtime shipped in the venv (nvidia/*/lib), not the host's.
NVIDIA_LIBS="$("${PYTHON_BIN}" -c 'import glob, os, nvidia; print(":".join(sorted(glob.glob(os.path.join(nvidia.__path__[0], "*", "lib")))))')"
export LD_LIBRARY_PATH="${NVIDIA_LIBS}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export SGL_DISABLE_TP_MEMORY_INBALANCE_CHECK="${SGL_DISABLE_TP_MEMORY_INBALANCE_CHECK:-1}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${NO_PROXY}"

if [[ "${SKIP_PREFLIGHT:-0}" != "1" && "${DRY_RUN:-0}" != "1" ]]; then
  "${PYTHON_BIN}" scripts/preflight.py \
    --model-path "${MODEL_PATH}" \
    --train "${TRAIN_FILE}" \
    --val "${VAL_FILE}" \
    --max-prompt-length "${MAX_PROMPT_LENGTH}"
fi

COMMAND=(
  "${PYTHON_BIN}" -m verl.trainer.main_ppo
  "${ADV_ARGS[@]}"
  algorithm.use_kl_in_reward=False
  algorithm.kl_penalty=low_var_kl
  algorithm.kl_ctrl.type=fixed
  "algorithm.kl_ctrl.kl_coef=${KL_COEF}"
  "data.train_files=${TRAIN_FILE}"
  "data.val_files=${VAL_FILE}"
  "data.train_batch_size=${TRAIN_BATCH_SIZE}"
  "data.max_prompt_length=${MAX_PROMPT_LENGTH}"
  "data.max_response_length=${MAX_RESPONSE_LENGTH}"
  data.filter_overlong_prompts=False
  data.truncation=error
  data.return_raw_chat=True
  "data.custom_cls.path=${ORPO_ROOT}/recipe/envscaler_openai_fc/dataset.py"
  data.custom_cls.name=OpenAIFCToolDataset
  "actor_rollout_ref.model.path=${MODEL_PATH}"
  actor_rollout_ref.model.use_remove_padding=True
  actor_rollout_ref.model.enable_gradient_checkpointing=True
  "actor_rollout_ref.actor.optim.lr=${ACTOR_LR}"
  "actor_rollout_ref.actor.ppo_mini_batch_size=${PPO_MINI_BATCH_SIZE}"
  "actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=${PPO_MICRO_BATCH_PER_GPU}"
  actor_rollout_ref.actor.ppo_epochs=1
  actor_rollout_ref.actor.use_kl_loss=True
  "actor_rollout_ref.actor.kl_loss_coef=${KL_COEF}"
  "actor_rollout_ref.actor.opd_loss_coef=${OPD_LOSS_COEF}"
  "actor_rollout_ref.actor.opd_gate_beta=${OPD_GATE_BETA}"
  actor_rollout_ref.actor.entropy_coeff=0
  "actor_rollout_ref.actor.fsdp_config.param_offload=${ACTOR_PARAM_OFFLOAD}"
  "actor_rollout_ref.actor.fsdp_config.optimizer_offload=${ACTOR_OPTIMIZER_OFFLOAD}"
  "actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=${PPO_MICRO_BATCH_PER_GPU}"
  "actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=${PPO_MICRO_BATCH_PER_GPU}"
  "actor_rollout_ref.ref.fsdp_config.param_offload=${REF_PARAM_OFFLOAD}"
  actor_rollout_ref.rollout.name=sglang
  actor_rollout_ref.rollout.mode=async
  "actor_rollout_ref.rollout.tensor_model_parallel_size=${TP_SIZE}"
  "actor_rollout_ref.rollout.gpu_memory_utilization=${GPU_MEMORY_UTILIZATION}"
  "actor_rollout_ref.rollout.n=${ROLLOUT_N}"
  "actor_rollout_ref.rollout.temperature=${ROLLOUT_TEMPERATURE}"
  "actor_rollout_ref.rollout.top_p=${ROLLOUT_TOP_P}"
  "actor_rollout_ref.rollout.free_cache_engine=${FREE_CACHE_ENGINE}"
  actor_rollout_ref.rollout.multi_turn.enable=True
  "actor_rollout_ref.rollout.multi_turn.max_assistant_turns=${MAX_ASSISTANT_TURNS}"
  actor_rollout_ref.rollout.multi_turn.max_parallel_calls=5
  "actor_rollout_ref.rollout.multi_turn.max_tool_response_length=${MAX_TOOL_RESPONSE_LENGTH}"
  actor_rollout_ref.rollout.multi_turn.tool_response_truncate_side=middle
  actor_rollout_ref.rollout.multi_turn.format=hermes
  "+actor_rollout_ref.rollout.multi_turn.max_tokens_per_step=${MAX_TOKENS_PER_STEP}"
  "+actor_rollout_ref.rollout.multi_turn.noise_rollout_fraction=${NOISE_ROLLOUT_FRACTION}"
  "+actor_rollout_ref.rollout.multi_turn.noise_rate=${NOISE_RATE}"
  "+actor_rollout_ref.rollout.multi_turn.noise_adv_split=${NOISE_ADV_SPLIT}"
  "actor_rollout_ref.rollout.agent.num_workers=${NUM_AGENT_WORKERS}"
  "actor_rollout_ref.rollout.agent.agent_loop_config_path=${ORPO_ROOT}/recipe/envscaler_openai_fc/agent_loop.yaml"
  actor_rollout_ref.rollout.val_kwargs.n=1
  actor_rollout_ref.rollout.val_kwargs.temperature=0.0
  actor_rollout_ref.rollout.val_kwargs.top_p=1.0
  actor_rollout_ref.rollout.val_kwargs.do_sample=False
  trainer.critic_warmup=0
  "trainer.logger=${LOGGER}"
  "trainer.project_name=${PROJECT_NAME}"
  "trainer.experiment_name=${EXP_NAME}"
  "trainer.n_gpus_per_node=${N_GPUS_PER_NODE}"
  "trainer.nnodes=${N_NODES}"
  "trainer.save_freq=${SAVE_FREQ}"
  "trainer.test_freq=${TEST_FREQ}"
  "trainer.val_before_train=${VAL_BEFORE_TRAIN}"
  "trainer.total_epochs=${TOTAL_EPOCHS}"
  "trainer.total_training_steps=${TOTAL_TRAINING_STEPS}"
  "trainer.default_local_dir=${CKPT_DIR}"
  "trainer.rollout_data_dir=${CKPT_DIR}/rollout_data"
  "trainer.validation_data_dir=${CKPT_DIR}/validation_data"
  "${EXTRA_ARGS[@]}"
  "$@"
)

echo "[ORPO] model=${MODEL_PATH}"
echo "[ORPO] adv=${ADV_ESTIMATOR} n=${ROLLOUT_N} noise_fraction=${NOISE_ROLLOUT_FRACTION} noise_rate=${NOISE_RATE} opd_coef=${OPD_LOSS_COEF} opd_beta=${OPD_GATE_BETA}"
echo "[ORPO] ckpt=${CKPT_DIR} steps=${TOTAL_TRAINING_STEPS}"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf '%q ' "${COMMAND[@]}"
  printf '\n'
  exit 0
fi

mkdir -p "${CKPT_DIR}"
exec "${COMMAND[@]}"
