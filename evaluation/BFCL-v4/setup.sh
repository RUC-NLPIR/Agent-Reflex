#!/usr/bin/env bash
# BFCL V4 runner: official gorilla evaluator pinned at 6ea5797, driven through the
# OpenAI-compatible adapter in runner/ (Serper replaces SerpAPI for web search).
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BENCH/../shared/env.sh"
PYTHON="${PYTHON:-3.10}" bash "$BENCH/runner/scripts/setup.sh"
