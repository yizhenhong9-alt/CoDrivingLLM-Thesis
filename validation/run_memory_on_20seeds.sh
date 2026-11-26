#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-XXXXXX)
finish() {
  code=$?
  trap - EXIT
  PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
    validation/collect_memory_batch.py "$run" || true
  printf 'Exit code: %s; original result directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/run_memory_on_20seeds.py --run-dir "$run" 2>&1 | tee "$run/console.txt"
