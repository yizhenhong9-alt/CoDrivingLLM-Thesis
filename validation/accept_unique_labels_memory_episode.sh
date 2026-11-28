#!/usr/bin/env bash
# M25: one seed0 real-Qwen memory-on episode, never the 20-seed batch.
set -euo pipefail
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
run=$(mktemp -d /home/nclab/Yizhen/runs/M25-memory-on-seed0-XXXXXX)
printf 'Result directory: %s\n' "$run"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis rev-parse HEAD > "$run/git-commit.txt"
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --porcelain=v1 > "$run/git-status.txt"
free -h > "$run/memory.txt"
df -h /home/nclab/Yizhen > "$run/disk.txt"
mkdir -p "$run/cache" "$run/matplotlib" "$run/tmp"
export PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME="$run/cache" MPLCONFIGDIR="$run/matplotlib" TMPDIR="$run/tmp"
set +e
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/accept_memory_episode.py --run-dir "$run" 2>&1 | tee "$run/console.txt"
traffic_code=${PIPESTATUS[0]}
set -e
printf '%s\n' "$traffic_code" > "$run/acceptance-exit-code.txt"
# Explicit evidence selection; do not export Chroma, service caches or model files.
(
  cd "$run"
  for file in git-commit.txt git-status.txt memory.txt disk.txt console.txt acceptance-exit-code.txt \
              memory-config.json acceptance.json service/service-console.txt service/ready.json; do
    if [ -f "$file" ]; then printf '%s\0' "$file"; fi
  done
  if [ -d live ]; then
    find live -type f \( -name result.json -o -name 'step-*.json' -o -name '*console.txt' -o -name review.md \) -print0
  fi
) > "$run/review-files.list"
tar -czf "${run}-review.tar.gz" -C "$run" --null -T "$run/review-files.list"
printf '\nAcceptance exit code: %s\nResult directory: %s\nReview archive: %s-review.tar.gz\n' "$traffic_code" "$run" "$run"
exit "$traffic_code"
