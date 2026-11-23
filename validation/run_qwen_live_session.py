"""M10/M12: launch one local model, validate traffic replies, optionally step, stop.

Spark only. Default no step; --apply-step applies exactly one step. No download,
installation, process-group signal or SIGKILL.
Use the existing inference interpreter. This command DOES consume shared GPU.
"""
import argparse
import math
from importlib import metadata
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.qwen_transport import LocalQwen

OWNER = Path("/home/nclab/Yizhen")
INFERENCE = OWNER / "envs/qwen-vllm034-py312/bin/python"
SIMULATION = OWNER / "envs/codriving-sim-py38/bin/python"
MODEL_DIR = OWNER / "models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4"
MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8"
REVISION = "5a5a776300a41aaa681dd7ff0106608ef2bc90db"


def memory_now():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            values[key] = int(value.split()[0]) * 1024
    return values


def listener_inodes(text, port=18080):
    return {line.split()[9] for line in text.splitlines()[1:] if len(line.split()) > 9
            and line.split()[3] == "0A"
            and int(line.split()[1].split(":")[-1], 16) == port}


def port_listeners():
    result = set()
    for name in ("tcp", "tcp6"):
        result.update(listener_inodes(Path("/proc/net/" + name).read_text()))
    return result


def process_info(pid):
    try:
        raw = Path("/proc/{}/stat".format(pid)).read_text()
        fields = raw[raw.rfind(")")+2:].split()
        return dict(pid=pid, ppid=int(fields[1]), pgid=int(fields[2]),
                    state=fields[0], start_ticks=int(fields[19]))
    except (OSError, ValueError, IndexError):
        return None


def family_snapshot(parent_pid):
    processes = [process_info(int(path.name)) for path in Path("/proc").iterdir() if path.name.isdigit()]
    processes = [item for item in processes if item is not None]
    ids = {parent_pid}
    while True:
        more = {item["pid"] for item in processes if item["ppid"] in ids}
        if more <= ids:
            break
        ids.update(more)
    return [item for item in processes if item["pid"] in ids or item["pgid"] == parent_pid]


def owns_listener(family, inodes):
    if not inodes:
        return False
    for item in family:
        try:
            for fd in Path("/proc/{}/fd".format(item["pid"])).iterdir():
                try:
                    if os.readlink(fd) in {"socket:[{}]".format(inode) for inode in inodes}:
                        return True
                except OSError:
                    pass
        except OSError:
            pass
    return False


def launch_args():
    return [str(INFERENCE), "-I", "-B", "-m", "vllm.entrypoints.openai.api_server",
            "--model", str(MODEL_DIR), "--served-model-name", MODEL,
            "--host", "127.0.0.1", "--port", "18080", "--max-model-len", "2048",
            "--max-num-seqs", "1", "--max-num-batched-tokens", "256", "--enforce-eager",
            "--moe-backend", "triton", "--kv-cache-memory-bytes", "536870912",
            "--gpu-memory-utilization", "0.40", "--load-format", "safetensors",
            "--shutdown-timeout", "30"]


def validate_rpc_path(path):
    # vLLM appends a 36-character UUID; Linux sockaddr_un allows 107 bytes.
    endpoint = path / "00000000-0000-0000-0000-000000000000"
    length = len(str(endpoint).encode("utf-8"))
    if length > 107:
        raise ValueError("RPC socket path would use {} bytes (limit 107): {}".format(length, endpoint))
    return length


def short_rpc_directory(owner):
    owner = owner.resolve()
    base = owner / ".rpc"
    base.resolve().relative_to(owner)
    path = base / uuid4().hex[:12]
    validate_rpc_path(path)
    base.mkdir(exist_ok=True)
    path.mkdir()  # Exclusive run directory; never reuse another run's sockets.
    return path


def environment(folder, gpu_uuid, *, owner=OWNER):
    folder.resolve().relative_to(owner.resolve())
    env = os.environ.copy()
    overrides = dict(CUDA_VISIBLE_DEVICES=gpu_uuid, CUDA_MODULE_LOADING="LAZY",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", VLLM_NO_USAGE_STATS="1",
        DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1",
        MPLBACKEND="Agg", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    for key, child in (("HF_HOME", "huggingface"), ("XDG_CACHE_HOME", "cache"),
                       ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                       ("TMPDIR", "tmp"), ("TEMP", "tmp"), ("TMP", "tmp"),
                       ("MPLCONFIGDIR", "matplotlib"), ("CUDA_CACHE_PATH", "cuda-cache"),
                       ("TRITON_CACHE_DIR", "triton-cache"), ("TORCH_EXTENSIONS_DIR", "torch-extensions"),
                       ("VLLM_CACHE_ROOT", "vllm-cache"), ("FLASHINFER_WORKSPACE_BASE", "flashinfer"),
                       ("TORCHINDUCTOR_CACHE_DIR", "torchinductor"), ("NUMBA_CACHE_DIR", "numba")):
        path = folder / child
        path.mkdir(exist_ok=True)
        overrides[key] = str(path)
    overrides["VLLM_RPC_BASE_PATH"] = str(short_rpc_directory(owner))
    env.update(overrides)
    return env, overrides


def parent_only_stop(proc, wait_seconds=120):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
    try:
        return dict(exited=True, exit_code=proc.wait(timeout=wait_seconds), signal_target="API parent only")
    except subprocess.TimeoutExpired:
        return dict(exited=False, signal_target="API parent only", manual_review_required=True)


def traffic_args(folder, parser_mode, seed, *, apply_step=False, project_entry=False,
                 max_steps=1, wall_seconds=1800):
    if project_entry:
        if apply_step:
            raise ValueError("Project entry applies steps itself; omit --apply-step")
        return [str(SIMULATION), "-B", str(ROOT / "Run_multi_CAV_LLM.py"),
                "--backend", "qwen", "--parser", parser_mode, "--seed", str(seed),
                "--max-steps", str(max_steps), "--wall-seconds", str(wall_seconds),
                "--output-dir", str(folder / "traffic")]
    command = [str(SIMULATION), "-B", str(ROOT / "validation/run_qwen_single_step.py"),
            "--mode", "live", "--parser", parser_mode, "--seed", str(seed),
            "--output-dir", str(folder / "traffic"), "--max-tokens", "256"]
    if apply_step:
        command.append("--apply-step")
    return command


def validate_session_paths(output_dir, repo, model_dir, interpreters, owner=OWNER):
    """Restrict writable/data directories, but allow a venv's binary symlink.

    The venv/bin directory must remain inside owner. The interpreter executable
    is read/executed only, and may resolve to a system or managed base Python.
    """
    owner = owner.resolve()
    result = {}
    for label, path in (("output_dir", output_dir), ("repository", repo), ("model_dir", model_dir)):
        resolved = path.resolve()
        try:
            resolved.relative_to(owner)
        except ValueError:
            raise ValueError("{}: requested={}; resolved={}; directory must stay inside {}".format(
                label, path, resolved, owner))
        result[label] = str(resolved)
    for label, path in interpreters.items():
        parent = path.parent.resolve()
        try:
            path.absolute().relative_to(owner)
            parent.relative_to(owner)
        except ValueError:
            raise ValueError("{}: requested={}; resolved bin directory={}; venv must stay inside {}".format(
                label, path, parent, owner))
        if not path.is_file():
            raise ValueError("{}: interpreter not found: {}".format(label, path))
        result[label] = dict(requested=str(path), resolved_executable=str(path.resolve()),
                             resolved_bin_directory=str(parent), access="execute/read only")
    return result


def system_snapshot():
    result = {}
    try:
        result["memory"] = memory_now()
    except OSError as exc:
        result["memory_error"] = str(exc)
    try:
        completed = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=20)
        result["nvidia_smi"] = dict(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["nvidia_smi_error"] = str(exc)
    return result


def validate_single_step_result(client, traffic, apply_step):
    expected = "single_step_complete" if apply_step else "validated_not_applied"
    if client.returncode != 0 or traffic.get("status") != expected:
        raise RuntimeError("Real response validation failed; retain original replies for review")
    if traffic.get("actual_environment_steps") != int(apply_step) or traffic.get("memory_module_imported"):
        raise RuntimeError("Unexpected step or memory state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--parser", choices=("strict", "legacy"), default="strict")
    parser.add_argument("--apply-step", action="store_true",
                        help="After all replies pass validation, apply exactly one simulator step")
    parser.add_argument("--project-entry", action="store_true",
                        help="Run Run_multi_CAV_LLM.py instead of single-step validation")
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--wall-seconds", type=float, default=1800)
    args = parser.parse_args()
    if args.project_entry and args.apply_step:
        parser.error("--project-entry applies steps; do not combine with --apply-step")
    if args.max_steps < 1 or not math.isfinite(args.wall_seconds) or args.wall_seconds <= 0:
        parser.error("Positive finite time and step limits required")
    if not args.project_entry and (args.max_steps != 1 or args.wall_seconds != 1800):
        parser.error("Step/time options require --project-entry")
    if sys.platform != "linux":
        parser.error("Run on Spark Linux only; this command launches the real model")
    try:
        checked_paths = validate_session_paths(args.output_dir, ROOT, MODEL_DIR,
            {"inference_python": INFERENCE, "simulation_python": SIMULATION})
    except ValueError as exc:
        parser.error(str(exc))
    if Path(sys.prefix).resolve() != INFERENCE.parent.parent.resolve():
        parser.error("Wrong environment: sys.prefix={}; expected={}".format(
            sys.prefix, INFERENCE.parent.parent))
    folder = args.output_dir.resolve() / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    report = dict(status="preflight", model=MODEL, expected_revision=REVISION,
                  scope="one simulator step" if args.apply_step else "real responses only, no env.step",
                  apply_step=args.apply_step, observed_environment_steps=None,
                  seed=args.seed, parser_mode=args.parser, model_started=False)
    report["project_entry"] = args.project_entry
    if args.project_entry:
        report["scope"] = "original project entry, bounded episode"
        report["max_steps"] = args.max_steps
        report["wall_seconds"] = args.wall_seconds
    report["checked_paths"] = checked_paths
    report["script_sha256"] = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    output, proc, client = folder / "result.json", None, None
    known = {}

    def save():
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(output)

    def remember():
        family = family_snapshot(proc.pid)
        for item in family:
            known[(item["pid"], item["start_ticks"])] = item
        return family

    try:
        if metadata.version("vllm") != "0.34.0":
            raise RuntimeError("Installed vLLM version changed; review before launch")
        source = Path(metadata.distribution("vllm").locate_file("vllm/engine/arg_utils.py"))
        source.resolve().relative_to(OWNER)
        if '"--shutdown-timeout"' not in source.read_text(encoding="utf-8"):
            raise RuntimeError("Installed shutdown-timeout option is absent")
        report["before"] = system_snapshot()
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                  capture_output=True, text=True, check=True)
        report["git_commit"] = revision.stdout.strip()
        memory = report["before"]["memory"]
        # Conservative launch gate, not a reservation or a proven memory limit.
        required = max(64 * 2**30, int(memory["MemTotal"] * 0.40))
        report["launch_gate_required_available_bytes"] = required
        if memory["MemAvailable"] < required:
            raise RuntimeError("Insufficient current available RAM for conservative launch gate")
        if port_listeners():
            raise RuntimeError("Port 18080 already has a listener; no existing service will be touched")
        if not (MODEL_DIR / "model.safetensors.index.json").is_file():
            raise RuntimeError("Expected local model index is missing")
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
                             capture_output=True, text=True, check=True, timeout=20).stdout.splitlines()
        if gpu != ["GPU-9dc7c211-0cb3-dc3c-9df6-67e50e4848db"]:
            raise RuntimeError("GPU UUID differs from original successful setup; inspect before launch")
        env, overrides = environment(folder, gpu[0])
        report["launch"] = dict(args=launch_args(), environment_overrides=overrides,
                                revision_evidence="Pinned local directory; no repeated weight verification")
        save()
        print("Run directory: " + str(folder), flush=True)
        print("Starting one real Qwen service; scope: " + report["scope"], flush=True)
        with (folder / "server-console.txt").open("w", encoding="utf-8") as console:
            proc = subprocess.Popen(launch_args(), cwd=str(folder), env=env,
                                    stdout=console, stderr=subprocess.STDOUT, start_new_session=True)
            report.update(model_started=True, server_pid=proc.pid)
            remember()
            save()
            transport = LocalQwen(timeout=2)
            started, last_update = time.monotonic(), -30
            while time.monotonic()-started < 1200:
                if proc.poll() is not None:
                    raise RuntimeError("Server exited before readiness; inspect server-console.txt")
                family = remember()
                ready = False
                if owns_listener(family, port_listeners()):
                    try:
                        report["models_response"] = transport.preflight()
                        ready = True
                    except Exception as exc:
                        report["last_readiness_error"] = str(exc)
                elapsed = time.monotonic()-started
                if elapsed-last_update >= 30:
                    print("Waiting for model: {}s; available {:.2f} GiB".format(int(elapsed), memory_now()["MemAvailable"]/2**30), flush=True)
                    last_update = elapsed
                if ready:
                    break
                time.sleep(2)
            else:
                raise RuntimeError("Readiness timeout; stop parent and inspect logs")
            report["status"] = "model_ready"
            save()
            print("Model ready; validating traffic replies; apply-step=" + str(args.apply_step), flush=True)
            command = traffic_args(folder, args.parser, args.seed, apply_step=args.apply_step,
                                   project_entry=args.project_entry, max_steps=args.max_steps,
                                   wall_seconds=args.wall_seconds)
            report["traffic_command"] = command
            with (folder / "traffic-console.txt").open("w", encoding="utf-8") as traffic_console:
                client = subprocess.Popen(command, cwd=str(ROOT), env=env,
                                          stdout=traffic_console, stderr=subprocess.STDOUT)
                client_deadline = time.monotonic()+args.wall_seconds+60
                while client.poll() is None:
                    if args.project_entry and time.monotonic() > client_deadline:
                        raise TimeoutError("Project client exceeded wall-time plus cleanup allowance")
                    if proc.poll() is not None:
                        raise RuntimeError("Model exited while traffic was running")
                    remember()
                    time.sleep(2)
            report["traffic_exit_code"] = client.returncode
            files = list((folder / "traffic").glob("*/result.json" if args.project_entry else "*.json"))
            if len(files) != 1:
                raise RuntimeError("Expected one traffic report; inspect traffic-console.txt")
            traffic = json.loads(files[0].read_text(encoding="utf-8"))
            report["traffic_report"] = str(files[0])
            report["observed_environment_steps"] = traffic.get("actual_environment_steps")
            if args.project_entry:
                if (client.returncode != 0 or traffic.get("status") not in
                        ("step_limit_reached", "episode_terminal") or
                        not 1 <= traffic.get("actual_environment_steps", 0) <= args.max_steps or
                        traffic.get("memory_module_imported") or
                        traffic.get("entry_point") != "Run_multi_CAV_LLM.py"):
                    raise RuntimeError("Project entry failed; retain step files and replies")
                report["status"] = ("project_episode_terminal" if traffic["status"] == "episode_terminal"
                                    else "project_step_limit_reached")
                report["parser_statistics"] = traffic.get("parser_statistics")
            else:
                validate_single_step_result(client, traffic, args.apply_step)
                report["status"] = "single_step_validated" if args.apply_step else "responses_validated"
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    finally:
        if client is not None and client.poll() is None:
            client.terminate()
            try:
                client.wait(timeout=10)
            except subprocess.TimeoutExpired:
                report["client_still_running"] = True
        if proc is not None:
            try:
                remember()
            except OSError as exc:
                report["process_tracking_error"] = str(exc)
            report["known_server_processes"] = list(known.values())
            print("Stopping API parent only; allowing up to 120s", flush=True)
            try:
                report["shutdown"] = parent_only_stop(proc)
            except OSError as exc:
                report["shutdown"] = dict(exited=False, error=str(exc), manual_review_required=True)
            # Observe asynchronous cleanup; do not signal remaining descendants.
            deadline = time.monotonic()+10
            remaining = []
            while True:
                remaining = [current for pid, ticks in known for current in [process_info(pid)]
                             if current is not None and current["start_ticks"] == ticks]
                if not remaining or time.monotonic() >= deadline:
                    break
                time.sleep(1)
            report["shutdown"]["remaining_known_processes"] = remaining
            report["shutdown"]["port_closed"] = not port_listeners()
            text = (folder / "server-console.txt").read_text(encoding="utf-8", errors="replace")
            report["shutdown"]["warnings"] = [name for name in (
                "EngineDeadError", "semaphore", "force killing", "Force killing") if name in text]
            clean = (report["shutdown"].get("exit_code") == 0 and not remaining and
                     report["shutdown"]["port_closed"] and not report["shutdown"]["warnings"])
            report["shutdown"]["clean_observation"] = clean
            if not clean or report.get("client_still_running"):
                report["status"] = "needs_shutdown_review"
        report["after"] = system_snapshot()
        save()
        print("Status: " + report["status"])
        print("Result: " + str(output))
    return 0 if report["status"] in ("responses_validated", "single_step_validated",
                                     "project_episode_terminal", "project_step_limit_reached") else 1


if __name__ == "__main__":
    raise SystemExit(main())
