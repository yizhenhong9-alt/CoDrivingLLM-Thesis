#!/usr/bin/env bash
# M24 zero-step full fixture prompts + offline tokenizer. No Qwen/memory service.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
diag=$(mktemp -d /home/nclab/Yizhen/runs/M24-vehicle-id-XXXXXX)
trap 'code=$?; printf "Exit code: %s; review directory: %s\n" "$code" "$diag"' EXIT
mkdir -p "$diag/cache" "$diag/matplotlib" "$diag/tmp"
export PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME="$diag/cache" MPLCONFIGDIR="$diag/matplotlib" TMPDIR="$diag/tmp"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$diag/git-commit.txt"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --porcelain=v1 > "$diag/git-status.txt"
for seed in 0 1; do
  /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
    validation/run_qwen_single_step.py --mode fixture --parser strict --seed "$seed" \
    --output-dir "$diag/seed-$seed" 2>&1 | tee "$diag/seed-$seed-console.txt"
done
/home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python \
  validation/count_qwen_prompt_tokens.py \
  --model-dir /home/nclab/Yizhen/models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4 \
  --fixtures "$diag"/seed-*/*.json --output-dir "$diag/tokens" \
  --output-tokens 256 --context-limit 2048 2>&1 | tee "$diag/token-console.txt"
# Export this isolated review directory only; never collect the existing DBs.
tar -czf "$diag/review.tar.gz" --exclude=review.tar.gz --exclude=cache --exclude=matplotlib --exclude=tmp -C "$diag" .
printf 'Review archive: %s/review.tar.gz\n' "$diag"
