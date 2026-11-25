"""Qwen integration for the original entry point; no model loading or launch."""
import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .qwen_step import MODEL, run_step
from .qwen_transport import LocalQwen

ROOT = Path(__file__).resolve().parents[1]


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    return value


def state(env):
    return [json_value(dict(vehicle_id=v.id, position=v.position,
                            speed_mps=v.speed, crashed=bool(v.crashed)))
            for v in env.controlled_vehicles]


def save(path, report):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(json_value(report), ensure_ascii=False,
                               indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def parser_counts(steps, selected="strict"):
    result = {}
    for stage in ("negotiation", "action"):
        calls = [c for s in steps for c in s.get("calls", []) if c["stage"] == stage]
        received = [c for c in calls if "raw_response" in c]
        parsed = sum(c.get("parsers", {}).get("strict", {}).get("status") == "parsed"
                     for c in received)
        selected_parsed = sum(c.get("parsers", {}).get(selected, {}).get("status") == "parsed"
                              for c in received)
        result[stage] = dict(attempted=len(calls), text_received=len(received),
                             strict_parsed=parsed, strict_not_parsed=len(received)-parsed,
                             no_text=len(calls)-len(received),
                             strict_success_rate=parsed/len(received) if received else None,
                             selected_parser=selected, selected_parsed=selected_parsed,
                             selected_success_rate=selected_parsed/len(received) if received else None)
    return result


class BudgetTransport:
    """Check session time before every request and bound its HTTP timeout."""
    mode = "live"

    def __init__(self, inner, seconds):
        self.inner, self.deadline = inner, time.monotonic()+seconds

    @property
    def last_response(self):
        return self.inner.last_response

    def remaining(self):
        remaining = self.deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Episode wall-time limit reached")
        self.inner.timeout = min(self.inner.timeout, remaining)

    def preflight(self):
        self.remaining()
        return self.inner.preflight()

    def complete(self, *args):
        self.inner.last_response = None
        self.remaining()
        return self.inner.complete(*args)


def run_episode(env, negotiation_cls, action_cls, transport, folder, *,
                parser_mode, episode_id, max_steps, persist_summary, summary,
                snapshot=state, memory_prompt=None):
    """Production loop, also exercised using test doubles without GPU/simulator."""
    steps = []
    summary.update(status="running", actual_environment_steps=0, step_files=[])
    for index in range(max_steps):
        step = dict(episode_id=episode_id, step_id=index, status="initializing",
                    initial_vehicles=snapshot(env), calls=[])
        if memory_prompt is not None:
            step['git_commit'] = summary.get('git_commit', 'unavailable')
        steps.append(step)
        path = folder / ("step-{:04d}.json".format(index))
        summary["step_files"].append(path.name)
        save(path, step)
        try:
            run_step(env, negotiation_cls(env), action_cls(env), transport, step,
                     parser_mode=parser_mode, episode_id=episode_id, step_id=index,
                     apply_step=True, persist=lambda value: save(path, value), memory_prompt=memory_prompt)
        except BaseException:
            step.update(status="failed", error=traceback.format_exc())
            summary["status"] = "failed"
            raise
        finally:
            step["final_vehicles"] = snapshot(env)
            step["actual_environment_steps"] = env.steps
            save(path, step)
            summary.update(actual_environment_steps=env.steps,
                           parser_statistics=parser_counts(steps, parser_mode))
            persist_summary(summary)
        print("Step {}: {}; actions={}".format(index, step["status"],
                                                step.get("submitted_vehicle_actions")), flush=True)
        if step["done"]:
            summary["status"] = "episode_terminal"
            return
    summary["status"] = "step_limit_reached"


def write_review(folder, summary):
    lines = ["# Qwen project entry observation", "", "Status: `"+summary["status"]+"`.",
             "", "Parser counts measure format extraction, not driving correctness.",
             "A step limit is not a completed episode. Terminal may include collision or timeout.",
             "", "```json", json.dumps(summary.get("parser_statistics", {}), indent=2), "```"]
    for name in summary.get("step_files", []):
        step = json.loads((folder/name).read_text(encoding="utf-8"))
        lines += ["", "## Step {}".format(step["step_id"]), "", "[Full prompt and state](./"+name+")"]
        for call in step.get("calls", []):
            lines += ["", "### {} vehicle={}".format(call["stage"], call["context"].get("vehicle_id")),
                      "", "Raw response (JSON string preserves exact content):", "", "```json",
                      json.dumps(call.get("raw_response"), ensure_ascii=False), "```",
                      "", "Parser results:", "", "```json",
                      json.dumps(call.get("parsers", {}), indent=2, ensure_ascii=False), "```"]
            if call.get("error"):
                lines += ["", "Request failed; inspect the full step JSON."]
    (folder/"review.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def main(args):
    if sys.platform != "linux":
        raise RuntimeError("Run Qwen simulation on Spark Linux; no local model is loaded")
    if args.max_steps < 1 or not math.isfinite(args.wall_seconds) or args.wall_seconds <= 0:
        raise ValueError("Positive finite time and step limits required")
    owner = Path("/home/nclab/Yizhen")
    ROOT.resolve().relative_to(owner)
    args.output_dir.resolve().relative_to(owner)
    episode = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8]
    folder = args.output_dir.resolve()/episode
    folder.mkdir(parents=True)
    summary = dict(status="initializing", episode_id=episode, model=MODEL,
                   entry_point="Run_multi_CAV_LLM.py", seed=args.seed,
                   parser_mode=args.parser, memory_mode="off", settings=vars(args).copy())
    summary["settings"]["output_dir"] = str(args.output_dir)
    if getattr(args, 'memory_config', None) is not None:
        summary['settings']['memory_config'] = str(args.memory_config)
    sources = list((ROOT/"llm_controller").glob("*.py"))+[ROOT/"Run_multi_CAV_LLM.py"]
    summary["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sources}
    for key, command in (("git_commit", ["rev-parse", "HEAD"]), ("git_status", ["status", "--porcelain=v1"])):
        summary[key] = subprocess.run(["git", "-c", "safe.directory="+ROOT.as_posix()]+command,
                                      cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.strip()
    persist = lambda value: save(folder/"result.json", value)
    persist(summary)
    env, memory_session = None, None
    memory_scope = ExitStack()
    code = 0
    try:
        if getattr(args, 'memory', 'off') == 'on':
            from .memory_mode import create_memory
            memory_session = memory_scope.enter_context(create_memory(None, 'on', args.memory_config))
            summary.update(memory_mode='on', memory_session=memory_session.receipt,
                           memory_method='original-per-vehicle-pre-step')
        # Preflight before constructing a simulation or calling an agent.
        transport = BudgetTransport(LocalQwen(), args.wall_seconds)
        summary["model_preflight"] = transport.preflight()
        import gym
        import highway_env
        if Path(highway_env.__file__).resolve().parent != ROOT/"highway_env":
            raise RuntimeError("Expected repository simulator")
        from .llm_agent_action import LlmAgent_action_module
        from .llm_agent_negotiation_system import LlmAgent_negotiation_module
        if "llm_controller.memory" in sys.modules:
            raise RuntimeError("Unexpected cloud memory import")
        env = gym.make("intersection-multi-agent-v0")
        env.reset(is_training=False, testing_seeds=args.seed)
        summary["config"] = json_value(env.config)
        run_episode(env, LlmAgent_negotiation_module, LlmAgent_action_module,
                    transport, folder, parser_mode=args.parser, episode_id=episode,
                    max_steps=args.max_steps, persist_summary=persist, summary=summary,
                    memory_prompt=memory_session)
    except (Exception, KeyboardInterrupt):
        summary.update(status="failed", error=traceback.format_exc())
        code = 1
    finally:
        try:
            memory_scope.close()
        except Exception:
            summary.update(status='failed', memory_close_error=traceback.format_exc())
            code = 1
        summary["memory_module_imported"] = "llm_controller.memory" in sys.modules
        if env is not None:
            summary["actual_environment_steps"] = env.steps
            try:
                env.close()
            except Exception:
                summary.update(status="failed", close_error=traceback.format_exc())
                code = 1
        persist(summary)
        write_review(folder, summary)
    print("Status: "+summary["status"])
    print("Result: "+str(folder/"result.json"))
    return code
