#!/usr/bin/env bash
# Full Agent-Reflex evaluation: serve the checkpoint once, then run every benchmark
# on its complete task set under the official settings.
#
#   MODEL_PATH=/path/to/checkpoint RUN_NAME=agent-reflex bash run_all.sh
#   BENCHES="Tau2 BFCL-v4" MODEL_PATH=... RUN_NAME=... bash run_all.sh   # a subset
#
# Scores land in outputs/<bench>/ (summary.json per run; BFCL-v4 also data_overall.csv).
set -uo pipefail
EVAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MODEL_PATH="${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}"
export RUN_NAME="${RUN_NAME:?set RUN_NAME, e.g. agent-reflex}"
export RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
BENCHES="${BENCHES:-Tau2 BFCL-v4 ACEBench VitaBench AgentNoiseBench ToolSandbox}"

bash "$EVAL/shared/serve_vllm.sh" || exit 1

declare -A STATUS
for bench in $BENCHES; do
  echo "=== $bench $(date -Is)"
  if bash "$EVAL/$bench/run.sh"; then STATUS[$bench]=done; else STATUS[$bench]="failed ($?)"; fi
done

echo "=== $RUN_NAME-$RUN_TAG"
for bench in $BENCHES; do printf '%-16s %s\n' "$bench" "${STATUS[$bench]}"; done
