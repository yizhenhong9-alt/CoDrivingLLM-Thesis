"""M05: intersection Qwen prompt/response validation; defaults to offline fixtures.

No model is loaded here. --mode live uses an already-running loopback service.
Only --mode live --apply-step may advance the simulator, exactly once.
"""
import argparse
from contextlib import redirect_stdout
from contextlib import ExitStack
from datetime import datetime, timezone
import io
import json
import hashlib
import os
from pathlib import Path
import sys
import subprocess
import traceback
from types import ModuleType
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smoke_intersection import git_revision, json_value, vehicle_state
from llm_controller.qwen_step import MODEL, run_step
from llm_controller.qwen_transport import LocalQwen, FixtureReplies


def load_agents():
    def reject(*args, **kwargs):
        raise RuntimeError("Original cloud SDK calls are disabled in M05")
    sdk = ModuleType("openai")
    sdk.OpenAI = reject
    with patch.dict(sys.modules, {"openai": sdk}):
        from llm_controller.llm_agent_action import LlmAgent_action_module
        from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module
    return LlmAgent_negotiation_module, LlmAgent_action_module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--parser", choices=("legacy", "strict"), default="strict")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--apply-step", action="store_true")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.apply_step and args.mode != "live":
        parser.error("Fixtures cannot be applied to traffic")
    if os.name == "posix":
        try:
            args.output_dir.resolve().relative_to(Path("/home/nclab/Yizhen"))
        except ValueError:
            parser.error("Spark outputs must stay inside /home/nclab/Yizhen")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    episode_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = args.output_dir / (episode_id + ".json")
    report = dict(status="initializing", episode_id=episode_id, git_commit=git_revision(),
                  python=sys.version, seed=args.seed, environment_steps=0,
                  model=MODEL, mode=args.mode, parser_mode=args.parser,
                  calls=[], settings=vars(args).copy())
    report["settings"]["output_dir"] = str(args.output_dir.resolve())
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in list((ROOT / "llm_controller").glob("*.py")) + [Path(__file__).resolve()]}
    git_command = ["git", "-c", "safe.directory=" + ROOT.as_posix()]
    for key, command in (("git_commit", ["rev-parse", "HEAD"]),
                         ("git_status", ["status", "--porcelain=v1"])):
        try:
            report[key] = subprocess.run(git_command + command, cwd=str(ROOT),
                capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            report[key] = None
    console, env, exit_code = io.StringIO(), None, 0

    def persist(value):
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(json_value(value), indent=2, ensure_ascii=False,
                                        allow_nan=False), encoding="utf-8")
        temporary.replace(output)

    transport = None
    try:
        with redirect_stdout(console), ExitStack() as stack:
            if args.mode == "fixture":
                def block_network(*unused, **unused_kwargs):
                    raise RuntimeError("Network disabled in fixture mode")
                for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
                    stack.enter_context(patch(target, block_network))
            import gym
            import highway_env
            if Path(highway_env.__file__).resolve().parent != ROOT / "highway_env":
                raise RuntimeError("Expected repository highway_env")
            negotiation_cls, action_cls = load_agents()
            if "llm_controller.memory" in sys.modules:
                raise RuntimeError("Unexpected memory module import")
            env = gym.make("intersection-multi-agent-v0")
            env.reset(is_training=False, testing_seeds=args.seed)
            report["config"] = json_value(env.config)
            report["initial_vehicles"] = [vehicle_state(v) for v in env.controlled_vehicles]
            transport = LocalQwen(args.port, args.timeout, args.max_tokens) if args.mode == "live" \
                else FixtureReplies(args.parser)
            if args.mode == "live":
                report["model_preflight"] = transport.preflight()
            run_step(env, negotiation_cls(env), action_cls(env), transport, report,
                     parser_mode=args.parser, episode_id=episode_id,
                     apply_step=args.apply_step, persist=persist)
    except Exception:
        report.update(status="failed", error=traceback.format_exc())
        exit_code = 1
    finally:
        if transport is not None and args.mode == "live":
            report["last_api_response"] = transport.last_response
        report["memory_module_imported"] = "llm_controller.memory" in sys.modules
        if env is not None:
            try:
                report["final_vehicles"] = [vehicle_state(v) for v in env.controlled_vehicles]
                report["actual_environment_steps"] = env.steps
            finally:
                try:
                    env.close()
                except Exception:
                    report["close_error"] = traceback.format_exc()
                    report["status"], exit_code = "failed", 1
        report["console"] = console.getvalue()
        persist(report)
    print("Status: " + report["status"])
    print("Result: " + str(output.resolve()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
