#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M21-R1-memory-prompt-XXXXXX)
trap 'code=$?; printf "Exit code: %s; result directory: %s\n" "$code" "$run"' EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python \
  validation/accept_memory_prompt.py --run-dir "$run" "$@" 2>&1 | tee "$run/console.txt"
