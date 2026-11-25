#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M20-R7-memory-http-XXXXXX)
trap 'code=$?; printf "Exit code: %s; result directory: %s\n" "$code" "$run"' EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short > "$run/git-status.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/accept_memory_http.py --run-dir "$run" 2>&1 | tee "$run/client-console.txt"
printf 'M20-R7 cross-environment isolated memory HTTP: PASS\n'
