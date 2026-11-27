#!/usr/bin/env bash
# Run ONE seed3 retry only after separate recovery review. Never auto-continue to4.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
if [ "$#" -ne 1 ]; then printf 'Provide the exact prepared seed3 retry directory.\n'; exit 2; fi
run=$1
case "$run" in /home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-seed3-retry-*) ;; *) exit 2 ;; esac
if [ ! -f "$run/seed3-recovery.json" ] || [ -e "$run/retry-started.json" ] || [ -e "$run/retry-result.json" ]; then
  printf 'Fresh prepared retry required; preserve all existing attempts.\n'; exit 2
fi
finish() {
  code=$?
  trap - EXIT
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B validation/collect_memory_batch.py "$run" || true
  printf 'Retry exit code: %s; result directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
export PYTHONDONTWRITEBYTECODE=1
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python -B \
  validation/run_m24_seed3_retry.py --run-dir "$run" 2>&1 | tee "$run/console.txt"
