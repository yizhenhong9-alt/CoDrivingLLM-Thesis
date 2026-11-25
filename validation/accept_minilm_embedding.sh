#!/usr/bin/env bash
# M20-R6: manual Spark invocation; no package installation or Qwen operations.
set -euo pipefail
owner=/home/nclab/Yizhen
repo="$owner/src/CoDrivingLLM-Thesis"
python="$owner/envs/memory-chroma0415-py312/bin/python"
run_dir=$(mktemp -d "$owner/runs/M20-R6-minilm-acceptance-XXXXXX")
trap 'code=$?; echo "Exit code: $code; result directory: $run_dir"' EXIT
mkdir -p "$run_dir/tmp" "$run_dir/xdg" "$run_dir/hf" "$run_dir/torch"
export TMPDIR="$run_dir/tmp" XDG_CACHE_HOME="$run_dir/xdg"
export HF_HOME="$run_dir/hf" TORCH_HOME="$run_dir/torch"
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_DISABLE_TELEMETRY=1
export ANONYMIZED_TELEMETRY=False CUDA_VISIBLE_DEVICES=''
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
cd "$repo"
git rev-parse HEAD | tee "$run_dir/git-commit.txt"
free -h | tee "$run_dir/memory.txt"
df -h "$owner" | tee "$run_dir/disk.txt"
"$python" validation/accept_minilm_embedding.py --run-dir "$run_dir" \
    2>&1 | tee "$run_dir/console.txt"
echo 'M20-R6 PASS: pinned MiniLM and isolated real-vector Chroma acceptance; production memory-on still pending.'
