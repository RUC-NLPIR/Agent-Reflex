#!/usr/bin/env bash
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMMIT=6ea57973c7a6097fd7c5915698c54c17c5b1b6c8
SOURCE="$ROOT/runtime/gorilla"
PYTHON_BIN=${PYTHON:-}

if test -z "$PYTHON_BIN"; then
  PYTHON_BIN=$(command -v python3.10 || command -v python3 || true)
fi
if test -z "$PYTHON_BIN"; then
  printf '%s\n' 'setup: Python 3.10+ is required' >&2
  exit 2
fi

pip_install() {
  unset UV_INDEX UV_EXTRA_INDEX_URL UV_INDEX_URL || true
  if command -v uv >/dev/null 2>&1; then
    case " $* " in
      *" --index-url "*)
        UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-180}" \
          uv pip install --python "$ROOT/.venv/bin/python" "$@"
        ;;
      *)
        UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-180}" \
          uv pip install --python "$ROOT/.venv/bin/python" \
          --index-url https://pypi.org/simple "$@"
        ;;
    esac
  else
    "$ROOT/.venv/bin/python" -m pip install "$@"
  fi
}

mkdir -p "$ROOT/runtime" "$ROOT/cache/huggingface"
if ! test -d "$SOURCE/.git"; then
  git clone --filter=blob:none --no-checkout \
    https://github.com/ShishirPatil/gorilla.git "$SOURCE"
fi
git -c "safe.directory=$SOURCE" -C "$SOURCE" fetch --depth 1 origin "$COMMIT"
git -c "safe.directory=$SOURCE" -C "$SOURCE" checkout --detach --force "$COMMIT"

BFCL_SRC=$(mktemp -d /tmp/bfcl_eval_src.XXXXXX)
cp -a "$SOURCE/berkeley-function-call-leaderboard/." "$BFCL_SRC/"
# Install with the test set shipped in BFCL-v4/data (identical to this commit).
rm -rf "$BFCL_SRC/bfcl_eval/data"
cp -a "$ROOT/../data" "$BFCL_SRC/bfcl_eval/data"

NEED_VENV=1
if test -x "$ROOT/.venv/bin/python" && "$ROOT/.venv/bin/python" -c 'import torch, pip' >/dev/null 2>&1; then
  NEED_VENV=0
fi
if test "$NEED_VENV" = 1; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --clear --python "$PYTHON_BIN" "$ROOT/.venv"
  else
    "$PYTHON_BIN" -m venv --clear "$ROOT/.venv"
  fi
  if ! "$ROOT/.venv/bin/python" -c 'import pip' >/dev/null 2>&1; then
    pip_install -U pip
  fi
  PY_MINOR=$("$ROOT/.venv/bin/python" -c 'import sys; print(sys.version_info.minor)')
  if test "${BFCL_SKIP_CPU_TORCH_PREINSTALL:-0}" != 1; then
    if test "$PY_MINOR" -le 11; then
      pip_install \
        --index-url https://download.pytorch.org/whl/cpu \
        'torch==2.13.0+cpu'
    else
      pip_install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch
    fi
  fi
fi

pip_install -r "$ROOT/../requirements.txt"
pip_install --no-deps "$BFCL_SRC"
pip_install --no-deps -e "$ROOT"

HF_HOME="$ROOT/cache/huggingface" \
  "$ROOT/.venv/bin/python" -c \
  'from sentence_transformers import SentenceTransformer; SentenceTransformer("all-MiniLM-L6-v2", device="cpu"); print("embedding_cache=PASS")'

"$ROOT/.venv/bin/python" -c \
  'import bfcl_eval, bfcl_boyue; print("bfcl_setup=PASS")'
