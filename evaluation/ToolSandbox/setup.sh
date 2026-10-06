#!/usr/bin/env bash
# apple/ToolSandbox at a pinned commit + Agent-Reflex roles: an OpenAI-compatible
# Qwen3_8B agent (local vLLM, thinking on) and a GPT_4_1 user on the Boyue gateway.
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

COMMIT=c8571d7854316d2e1c5f288e59fe1e34e53f6dd1
SRC="$RUNTIME/ToolSandbox"
ENV_DIR="$RUNTIME/toolsandbox-env"

if [[ ! -d "$SRC/.git" ]]; then
  git clone https://github.com/apple/ToolSandbox.git "$SRC"
fi
git -C "$SRC" checkout -q --force "$COMMIT"
git -C "$SRC" apply "$BENCH/toolsandbox_agent_reflex.patch"

uv venv --python 3.12 --seed "$ENV_DIR"
# Upstream pins openai==1.17.0, which passes `proxies=` that httpx 0.28 removed.
uv pip install --python "$ENV_DIR/bin/python" -e "$SRC" 'httpx==0.27.2'
"$ENV_DIR/bin/tool_sandbox" --help >/dev/null && echo "ToolSandbox ready"
