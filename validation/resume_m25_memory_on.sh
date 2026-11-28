#!/usr/bin/env bash
# Explicit second stage: use only a prepared M25 396-copy, never create/recover a DB here.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
if [ "$#" -ne 1 ]; then printf 'Provide the exact previously prepared M25 run directory.\n'; exit 2; fi
run=$1
case "$run" in /home/nclab/Yizhen/runs/M25-intersection-memory-on-20seeds-*) ;; *) exit 2 ;; esac
if [ ! -f "$run/retained-seed0.json" ] || [ -e "$run/batch-result.json" ]; then
  printf 'Prepared receipt required; do not retry an existing batch.\n'; exit 2
fi
finish() {
  code=$?
  trap - EXIT
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B validation/collect_memory_batch.py "$run" || true
  printf 'Batch exit code: %s; result directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
export PYTHONDONTWRITEBYTECODE=1
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B \
  validation/run_m25_memory_on_20seeds.py --run-dir "$run" \
  --retained-m25-source /home/nclab/Yizhen/runs/M25-memory-on-seed0-9lGes4 \
  2>&1 | tee "$run/console.txt"
