#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
diag=$(mktemp -d /home/nclab/Yizhen/runs/M23-R6-label-probe-XXXXXX)
trap 'code=$?; printf "Exit code: %s; diagnostic directory: %s\n" "$code" "$diag"' EXIT
mkdir -p "$diag/cache" "$diag/matplotlib" "$diag/tmp"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$diag/git-commit.txt"
PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME="$diag/cache" MPLCONFIGDIR="$diag/matplotlib" TMPDIR="$diag/tmp" \
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/run_qwen_single_step.py --mode fixture --parser strict --seed 1 \
  --output-dir "$diag/capture" 2>&1 | tee "$diag/console.txt"
