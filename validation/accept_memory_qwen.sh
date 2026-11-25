#!/usr/bin/env bash
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M21-R3-memory-qwen-XXXXXX)
trap 'code=$?; printf "Exit code: %s; result directory: %s\n" "$code" "$run"' EXIT
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python \
  validation/prepare_memory_replay.py --run-dir "$run" 2>&1 | tee "$run/preflight-console.txt"
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python \
  validation/run_qwen_live_session.py --output-dir "$run/live" \
  --memory-replay-config "$run/replay-config.json" 2>&1 | tee "$run/live-console.txt"
