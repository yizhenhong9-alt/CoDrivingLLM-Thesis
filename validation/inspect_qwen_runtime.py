"""M09: read-only Spark runtime/resource snapshot, without importing vLLM/torch.

Only report files are written. No model launch, HTTP request, signal, package
installation, GPU compute or weight verification is performed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

OWNER_ROOT = Path("/home/nclab/Yizhen")
MODEL_DIR = OWNER_ROOT / "models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4"
PATTERN = re.compile(r"SIGTERM|SIGINT|shutdown_timeout|shutdown-timeout|def shutdown|"
                     r"killpg|terminate\(|Popen|start_new_session|timeout_graceful_shutdown")


def memory_values(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB", line)
        if match:
            result[match[1] + "_bytes"] = int(match[2]) * 1024
    return result


def source_excerpt(path, radius=4, limit=100):
    raw = path.read_bytes()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = set()
    for index, line in enumerate(lines):
        if PATTERN.search(line):
            selected.update(range(max(0, index-radius), min(len(lines), index+radius+1)))
    ordered = sorted(selected)
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                truncated=len(ordered) > limit,
                lines=[{"line": index+1, "text": lines[index]} for index in ordered[:limit]])


def command_snapshot(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        return dict(command=command, exit_code=result.returncode,
                    stdout=result.stdout[:40000], stderr=result.stderr[:4000])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(command=command, error=str(exc))


def allowed(path):
    path.resolve().relative_to(OWNER_ROOT)
    return path.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run this collector on Spark Linux only")
    try:
        output_root = allowed(args.output_dir)
    except ValueError:
        parser.error("Output must stay inside /home/nclab/Yizhen")
    folder = output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    report = dict(status="snapshot_collected", utc=datetime.now(timezone.utc).isoformat(),
                  python=sys.version, executable=sys.executable, packages={}, source_excerpts=[],
                  historical_evidence={}, warnings=[],
                  model_started=False, signals_sent=False, packages_changed=False,
                  limitation="Point-in-time snapshot, not reserved resources or approval to launch")
    try:
        report["memory"] = memory_values(Path("/proc/meminfo").read_text())
        report["load_average"] = list(os.getloadavg())
        disk = shutil.disk_usage(OWNER_ROOT)
        report["owner_filesystem_bytes"] = dict(total=disk.total, used=disk.used, free=disk.free)
        for name in ("vllm", "torch", "transformers", "uvicorn", "flashinfer-python"):
            try:
                report["packages"][name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                report["packages"][name] = None
        dist = metadata.distribution("vllm")
        package = allowed(Path(dist.locate_file("vllm")))
        report["installed_vllm_root"] = str(package)
        for name in ("entrypoints/cli/serve.py", "entrypoints/openai/api_server.py",
                     "entrypoints/launchers/launcher.py", "entrypoints/launchers/api_server/entry.py",
                     "entrypoints/common/cli_args.py", "engine/arg_utils.py", "config/vllm.py",
                     "v1/engine/utils.py", "v1/engine/core_client.py", "v1/engine/async_llm.py", "v1/utils.py"):
            path = allowed(package / name)
            if path.is_file():
                report["source_excerpts"].append(source_excerpt(path))
        report["model_metadata_present"] = {
            name: (MODEL_DIR / name).is_file() for name in (
                "config.json", "tokenizer_config.json", "model.safetensors.index.json")}
        # Read bounded historical metadata, not weights or old tests.
        history = OWNER_ROOT / "runs/step8J-R1-api-smoke-d41rak3z"
        for name in ("launch-config.json", "result.json"):
            path = allowed(history / name)
            if path.is_file():
                raw = path.read_bytes()
                if len(raw) > 200000:
                    report["warnings"].append("Historical JSON too large: " + str(path))
                else:
                    report["historical_evidence"][name] = dict(path=str(path),
                        sha256=hashlib.sha256(raw).hexdigest(), data=json.loads(raw.decode("utf-8-sig")))
            else:
                report["warnings"].append("Missing historical evidence: " + str(path))
        script = allowed(history / "run-smoke.py")
        if script.is_file():
            report["historical_evidence"]["run-smoke.py"] = source_excerpt(script, radius=5)
        else:
            report["warnings"].append("Missing historical launch/stop script: " + str(script))
    except Exception as exc:
        report.update(status="incomplete", error=type(exc).__name__ + ": " + str(exc))
    report["commands"] = [command_snapshot(command) for command in (
        ["nvidia-smi"], ["ss", "-ltnp", "sport = :18080"], ["ps", "-eo", "pid,ppid,pgid,comm"])]
    if any(item.get("exit_code") != 0 for item in report["commands"]):
        report["status"] = "incomplete"
    report["forbidden_modules_imported"] = [name for name in ("torch", "vllm") if name in sys.modules]
    output = folder / "result.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Status: " + report["status"])
    print("MemAvailable GiB: " + str(round(report.get("memory", {}).get("MemAvailable_bytes", 0) / 2**30, 2)))
    print("vLLM: " + str(report["packages"].get("vllm")))
    print("Model started: false; signals sent: false")
    print("Result: " + str(output.resolve()))
    return 0 if report["status"] == "snapshot_collected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
