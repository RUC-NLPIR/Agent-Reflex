#!/usr/bin/env bash
# Serve the model under test with the paper protocol and wait until it is ready.
#
#   MODEL_PATH=/path/to/checkpoint bash shared/serve_vllm.sh
#
# Protocol: TP=8, bf16, hermes tool parser, deepseek_r1 reasoning parser and the
# force-thinking Qwen3 chat template, at Qwen3's native 40,960-token context.
# vLLM refuses a larger MAX_MODEL_LEN unless RoPE scaling is configured; forcing
# it past the rotary table triggers a device-side assert mid-run.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

MODEL_PATH="${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}"
VLLM="${VLLM:-$RUNTIME/vllm-env/bin/vllm}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-40960}"
LOG_FILE="${LOG_FILE:-$OUTPUT_ROOT/vllm-${PORT}.log}"
export MODEL_PATH

if assert_served_model 2>/dev/null; then
  echo "vLLM already serving $MODEL_PATH on :$PORT"
  exit 0
fi
if curl --noproxy '*' --max-time 5 -fsS "$AGENT_BASE_URL/models" >/dev/null 2>&1; then
  echo "Port $PORT already serves a different model; stop it or choose another PORT." >&2
  exit 1
fi

export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_ALLREDUCE_USE_SYMM_MEM=0

args=(
  serve "$MODEL_PATH"
  --served-model-name "$SERVED_MODEL_NAME"
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-8}"
  --host 0.0.0.0 --port "$PORT"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.90}"
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "${MAX_NUM_SEQS:-256}"
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS:-32768}"
  --dtype bfloat16 --trust-remote-code
  --enable-auto-tool-choice --tool-call-parser hermes
  --reasoning-parser deepseek_r1
  --chat-template "$CHAT_TEMPLATE_PATH"
  --enable-prefix-caching
  --attention-backend TRITON_ATTN
  --disable-custom-all-reduce
)

mkdir -p "$(dirname "$LOG_FILE")"
setsid nohup "$VLLM" "${args[@]}" >"$LOG_FILE" 2>&1 &
echo "vLLM pid $! starting, log: $LOG_FILE"

for _ in $(seq 1 180); do
  if assert_served_model 2>/dev/null; then
    echo "vLLM ready: $SERVED_MODEL_NAME -> $MODEL_PATH on :$PORT"
    exit 0
  fi
  sleep 5
done
echo "vLLM did not become ready in 15 min; see $LOG_FILE" >&2
exit 1
