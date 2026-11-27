#!/usr/bin/env bash
# COPY recovery only, no traffic/model startup. User runs manually on Spark.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-seed3-retry-XXXXXX)
finish() {
  code=$?
  trap - EXIT
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B validation/collect_memory_batch.py "$run" || true
  printf 'Preparation exit code: %s; prepared retry directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
export PYTHONDONTWRITEBYTECODE=1
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --porcelain=v1 > "$run/git-status.txt"
if [ -s "$run/git-status.txt" ]; then printf 'Checkout has edits; preserve them and stop.\n'; exit 1; fi
/home/nclab/Yizhen/envs/memory-chroma0415-py312/bin/python -B \
  validation/recover_m24_seed3.py \
  --source /home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-PvMXov \
  --run-dir "$run" 2>&1 | tee "$run/preparation-console.txt"
