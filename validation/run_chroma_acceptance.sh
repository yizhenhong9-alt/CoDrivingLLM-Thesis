#!/usr/bin/env bash
# M20-R3: manual Spark-only Chroma install and synthetic-vector acceptance.
set -euo pipefail

owner=/home/nclab/Yizhen
memory_env="$owner/envs/memory-chroma0415-py312"
memory_python="$memory_env/bin/python"
uv="$owner/bin/uv"
repo="$owner/src/CoDrivingLLM-Thesis"

test "$(uname -s)" = Linux
test -x "$uv"
test -x "$memory_python"
test -f "$repo/validation/check_chroma_memory.py"
test -f "$repo/modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json"

# The executable may symlink to the base Python, but the venv prefix must match.
"$memory_python" - "$memory_env" <<'PY'
import importlib.metadata as md
from pathlib import Path
import sys
expected = Path(sys.argv[1])
assert Path(sys.prefix) == expected, sys.prefix
expected.resolve().relative_to(Path('/home/nclab/Yizhen').resolve())
for name, version in [('numpy', '1.26.4'), ('chroma-hnswlib', '0.7.3')]:
    assert md.version(name) == version, (name, md.version(name))
print('Environment guard: PASS')
PY

mkdir -p "$owner/runs"
run_dir=$(mktemp -d "$owner/runs/M20-R3-chroma-XXXXXX")
trap 'code=$?; echo "Exit code: $code; result directory: $run_dir"' EXIT
mkdir -p "$run_dir/cache" "$run_dir/tmp" "$run_dir/xdg"

export UV_CACHE_DIR="$run_dir/cache"
export TMPDIR="$run_dir/tmp"
export XDG_CACHE_HOME="$run_dir/xdg"
export UV_PYTHON_DOWNLOADS=never
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export ANONYMIZED_TELEMETRY=False

cd "$repo"
git rev-parse HEAD | tee "$run_dir/git-commit.txt"
git status --short | tee "$run_dir/git-status.txt"
"$uv" --no-config pip freeze --python "$memory_python" > "$run_dir/packages-before.txt"

cat > "$run_dir/constraints.txt" <<'EOF'
numpy==1.26.4
chroma-hnswlib==0.7.3
pydantic<2
posthog<4
setuptools==75.8.0
wheel==0.45.1
pybind11==2.13.6
EOF

# --no-build reuses installed/cached packages but refuses any new source build.
# Do not remove this guard if a second platform dependency is unavailable.
"$uv" --no-config pip install --python "$memory_python" \
    --index-url https://pypi.org/simple --no-build --dry-run \
    --constraint "$run_dir/constraints.txt" 'chromadb==0.4.15' \
    2>&1 | tee "$run_dir/dependency-plan.console.txt"

"$uv" --no-config pip install --python "$memory_python" \
    --index-url https://pypi.org/simple --no-build \
    --constraint "$run_dir/constraints.txt" 'chromadb==0.4.15' \
    2>&1 | tee "$run_dir/install.console.txt"

"$uv" --no-config pip check --python "$memory_python" \
    2>&1 | tee "$run_dir/pip-check.console.txt"
"$uv" --no-config pip freeze --python "$memory_python" > "$run_dir/packages-after.txt"

"$memory_python" validation/check_chroma_memory.py --real-chroma \
    2>&1 | tee "$run_dir/chroma-tests.console.txt"

echo 'M20-R3 Chroma acceptance: PASS; true MiniLM retrieval remains unverified.'
