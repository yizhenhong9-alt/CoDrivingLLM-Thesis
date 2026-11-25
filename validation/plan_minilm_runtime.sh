#!/usr/bin/env bash
# M20-R4: metadata/dry-run only, never install packages or download model weights.
set -euo pipefail
owner=/home/nclab/Yizhen
repo="$owner/src/CoDrivingLLM-Thesis"
python="$owner/envs/memory-chroma0415-py312/bin/python"
uv="$owner/bin/uv"
baseline="$owner/runs/M20-R3-chroma-ziPNpa/packages-after.txt"
test -x "$python"
test -x "$uv"
test -f "$baseline"
run_dir=$(mktemp -d "$owner/runs/M20-R4-minilm-plan-XXXXXX")
trap 'code=$?; echo "Exit code: $code; result directory: $run_dir"' EXIT
mkdir -p "$run_dir/cache" "$run_dir/tmp"
export UV_CACHE_DIR="$run_dir/cache"
export TMPDIR="$run_dir/tmp"
export UV_PYTHON_DOWNLOADS=never
export PYTHONDONTWRITEBYTECODE=1
cd "$repo"
git rev-parse HEAD | tee "$run_dir/git-commit.txt"
free -h | tee "$run_dir/memory.txt"
df -h "$owner" | tee "$run_dir/disk.txt"
"$python" validation/plan_minilm_runtime.py --baseline "$baseline" --output-dir "$run_dir" \
    2>&1 | tee "$run_dir/preflight.console.txt"
"$uv" --no-config pip install --python "$python" \
    --index-url https://pypi.org/simple --no-build --dry-run \
    --constraint "$run_dir/constraints.txt" --requirement "$run_dir/requirements.in" \
    2>&1 | tee "$run_dir/dependency-plan.console.txt"
"$uv" --no-config pip freeze --python "$python" > "$run_dir/packages-after-plan.txt"
"$python" - "$baseline" "$run_dir/packages-after-plan.txt" <<'PY'
from pathlib import Path
import sys
from validation.plan_minilm_runtime import freeze_map
assert freeze_map(Path(sys.argv[1]).read_text()) == freeze_map(Path(sys.argv[2]).read_text())
print('M20-R4 plan: PASS; package baseline unchanged; no model downloaded or loaded.')
PY
