#!/usr/bin/env bash
# meituan-longcat/vitabench at a pinned commit + a small harness patch (gateway
# credentials from env, OpenAI-clean request bodies, non-interactive resume,
# judge = claude-sonnet-4-6). Task data is the copy shipped in VitaBench/data.
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"

COMMIT=742e240855bf8686a0842360749d5ea970ea3987
SRC="$RUNTIME/vitabench"
ENV_DIR="$RUNTIME/vita-env"

if [[ ! -d "$SRC/.git" ]]; then
  git clone https://github.com/meituan-longcat/vitabench.git "$SRC"
fi
# Drop the data symlink first so a forced checkout never writes into VitaBench/data.
[[ -L "$SRC/data/vita/domains" ]] && rm "$SRC/data/vita/domains"
git -C "$SRC" checkout -q --force "$COMMIT"
git -C "$SRC" apply "$BENCH/vitabench_agent_reflex.patch"
rm -rf "$SRC/data/vita/domains"
ln -s "$BENCH/data/vita/domains" "$SRC/data/vita/domains"

uv venv --python 3.12 --seed "$ENV_DIR"
uv pip install --python "$ENV_DIR/bin/python" -e "$SRC"
"$ENV_DIR/bin/vita" --help >/dev/null && echo "VitaBench ready"
