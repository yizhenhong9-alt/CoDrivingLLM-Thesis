#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M22-R1-original-memory-XXXXXX)
trap 'code=$?; printf "Exit code: %s; result directory: %s\n" "$code" "$run"' EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/accept_original_memory.py --run-dir "$run" 2>&1 | tee "$run/console.txt"
