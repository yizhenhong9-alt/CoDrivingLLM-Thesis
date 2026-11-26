#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
source_run=/home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-Y6aiqi
run=$(mktemp -d /home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-recovery-XXXXXX)
finish() {
  code=$?
  trap - EXIT
  PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
    validation/collect_memory_batch.py "$run" || true
  printf 'Exit code: %s; recovery result directory: %s\n' "$code" "$run"
  exit "$code"
}
trap finish EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/memory-chroma0415-py312/bin/python \
  validation/recover_memory_batch.py --source "$source_run" --run-dir "$run" \
  2>&1 | tee "$run/preparation-console.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/run_memory_on_20seeds.py --run-dir "$run" --recovery-source "$source_run" \
  2>&1 | tee "$run/console.txt"
