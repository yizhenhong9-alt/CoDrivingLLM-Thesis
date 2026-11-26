#!/usr/bin/env bash
# Prepare COPY only; no Qwen, traffic, embedding model or formal batch startup.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
source_run=/home/nclab/Yizhen/runs/M24-memory-on-seed0-VW3SSn
run=$(mktemp -d /home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-XXXXXX)
finish() {
  code=$?
  trap - EXIT
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B validation/collect_memory_batch.py "$run" || true
  printf 'Preparation exit code: %s; prepared run directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
export PYTHONDONTWRITEBYTECODE=1
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --porcelain=v1 > "$run/git-status.txt"
if [ -s "$run/git-status.txt" ]; then printf 'Checkout has edits; stop and preserve them.\n'; exit 1; fi
/home/nclab/Yizhen/envs/memory-chroma0415-py312/bin/python -B \
  validation/retain_m24_seed0.py --source "$source_run" --run-dir "$run" \
  2>&1 | tee "$run/preparation-console.txt"
