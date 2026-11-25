#!/usr/bin/env bash
# M20-R5: install only the reviewed step4 CPU runtime, never model weights.
set -euo pipefail
owner=/home/nclab/Yizhen
repo="$owner/src/CoDrivingLLM-Thesis"
python="$owner/envs/memory-chroma0415-py312/bin/python"
uv="$owner/bin/uv"
plan_dir="$owner/runs/M20-R4-minilm-plan-EbHo7u"
test -x "$python"
test -x "$uv"
test -f "$plan_dir/plan.json"
run_dir=$(mktemp -d "$owner/runs/M20-R5-minilm-runtime-XXXXXX")
trap 'code=$?; echo "Exit code: $code; result directory: $run_dir"' EXIT
mkdir -p "$run_dir/tmp" "$run_dir/xdg" "$run_dir/hf" "$run_dir/torch"
export UV_CACHE_DIR="$plan_dir/cache"
export TMPDIR="$run_dir/tmp"
export XDG_CACHE_HOME="$run_dir/xdg"
export HF_HOME="$run_dir/hf"
export TORCH_HOME="$run_dir/torch"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export ANONYMIZED_TELEMETRY=False
export CUDA_VISIBLE_DEVICES=''
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
export UV_PYTHON_DOWNLOADS=never
export PYTHONDONTWRITEBYTECODE=1
cd "$repo"
git rev-parse HEAD | tee "$run_dir/git-commit.txt"
free -h | tee "$run_dir/memory.txt"
df -h "$owner" | tee "$run_dir/disk.txt"
"$python" validation/verify_minilm_install.py --phase before \
    --plan-dir "$plan_dir" --output-dir "$run_dir" 2>&1 | tee "$run_dir/before.console.txt"
"$uv" --no-config pip install --python "$python" --index-url https://pypi.org/simple \
    --no-build --constraint "$plan_dir/constraints.txt" --requirement "$run_dir/install-requirements.txt" \
    2>&1 | tee "$run_dir/install.console.txt"
"$uv" --no-config pip check --python "$python" 2>&1 | tee "$run_dir/pip-check.console.txt"
"$python" validation/verify_minilm_install.py --phase after \
    --plan-dir "$plan_dir" --output-dir "$run_dir" 2>&1 | tee "$run_dir/after.console.txt"
"$uv" --no-config pip freeze --python "$python" > "$run_dir/packages-after.txt"
"$python" validation/verify_minilm_install.py --phase runtime \
    --plan-dir "$plan_dir" --output-dir "$run_dir" 2>&1 | tee "$run_dir/runtime.console.txt"
# New dependencies justify one focused regression of the verified Chroma path.
"$python" validation/check_chroma_memory.py --real-chroma \
    2>&1 | tee "$run_dir/chroma-tests.console.txt"
echo 'M20-R5 runtime: PASS; CPU imports/tensor and Chroma regression passed; MiniLM not downloaded or loaded.'
