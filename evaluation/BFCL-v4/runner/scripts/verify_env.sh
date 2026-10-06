#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export HF_HOME="$ROOT/cache/huggingface"
"$ROOT/.venv/bin/python" - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
print("embedding_cache=PASS", flush=True)
PY
./bfcl doctor
./bfcl models | grep qwen3-8b-local
