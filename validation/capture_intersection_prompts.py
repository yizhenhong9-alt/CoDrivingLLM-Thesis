"""Capture original prompts offline; fixture responses are NOT driving decisions."""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smoke_intersection import git_revision, json_value, vehicle_state


def capture(args, report):
    import gym
    import highway_env
    import numpy as np
    import pandas as pd

    # Offline capture does not require installing either cloud SDK dependency.
    # Supply only the names used by the original modules, with fail-closed defaults.
    def reject_sdk(*unused_args, **unused_kwargs):
        raise RuntimeError("Real SDK use is disabled in offline capture")

    httpx = ModuleType("httpx")
    httpx.Client = reject_sdk
    openai = ModuleType("openai")
    openai.OpenAI = reject_sdk
    sdk_stubs = {"openai": openai, "httpx": httpx}
    with patch.dict(sys.modules, sdk_stubs):
        import llm_controller.llm_agent_negotiation_system as negotiation
        import llm_controller.llm_agent_action as action
    report["sdk_mode"] = "in-process offline stubs; no installed openai/httpx required"

    if Path(highway_env.__file__).resolve().parent != ROOT / "highway_env":
        raise RuntimeError("Expected repository highway_env")
    report["versions"] = {
        "gym": gym.__version__, "numpy": np.__version__, "pandas": pd.__version__,
    }
    report["environment_source"] = str(Path(highway_env.__file__).resolve())
    if "llm_controller.memory" in sys.modules:
        raise RuntimeError("Memory module was unexpectedly imported")
    env = gym.make("intersection-multi-agent-v0")
    try:
        env.reset(is_training=False, testing_seeds=args.seed)
        report["config"] = json_value(env.config)
        report["initial_vehicles"] = [vehicle_state(v) for v in env.controlled_vehicles]
        agent_n = negotiation.LlmAgent_negotiation_module(env)
        conflicts = agent_n.detect_conflicts(env)
        vehicles = list(env.controlled_vehicles)
        names = {v: str(v).split(":")[0].strip() for v in vehicles}
        if len(set(names.values())) != len(vehicles):
            raise RuntimeError("Author prompt identifiers collided; cannot build unambiguous fixture")
        report["vehicle_identifiers"] = [
            {"simulation_id": v.id, "prompt_id": names[v]} for v in vehicles
        ]
        pairs, decisions = [], []
        for i, v in enumerate(vehicles):
            for other in vehicles[:i]:
                if other in conflicts[v] and v in conflicts[other]:
                    pairs.append({
                        "vehicle_i": names[v], "vehicle_j": names[other],
                        "distance_i_m": float(conflicts[v][other]),
                        "distance_j_m": float(conflicts[other][v]),
                    })
                    # Fixed ID order is a fixture only, with no safety claim.
                    first, second = sorted((v, other), key=lambda item: item.id)
                    decisions.append({"first_vehicle": names[first], "second_vehicle": names[second]})
        fixture = "Final Answer:\n" + json.dumps({"decisions": decisions})
        report["conflict_pairs"] = pairs
        report["negotiation_fixture"] = fixture
        report["fixture_rule"] = "Lower simulation ID first; arbitrary test order, not a safety policy"

        def record(stage):
            def create(**kwargs):
                response = fixture if stage == "negotiation" else 'Final Answer:\n    "decision": {"IDLE"}'
                report["calls"].append({
                    "stage": stage,
                    "original_model_argument": kwargs.get("model"),
                    "messages": kwargs["messages"],
                    "fixture_response": response,
                    "sent_to_model": False,
                })
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])
            return lambda **kwargs: SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )

        def block_network(*unused_args, **unused_kwargs):
            raise RuntimeError("Network access blocked by offline prompt capture")

        # Original SDK constructors are replaced before send_to_chatgpt executes.
        # No endpoint/key/proxy is used. Patches are scoped to this process/block.
        with patch.dict(sys.modules, sdk_stubs), \
                patch.object(negotiation, "OpenAI", record("negotiation")), \
                patch.object(action, "OpenAI", record("action")), \
                patch.object(httpx, "Client", lambda **kwargs: None), \
                patch("socket.socket.connect", block_network), \
                patch("socket.socket.connect_ex", block_network), \
                patch("socket.create_connection", block_network):
            negotiation_text, conflicting_info = agent_n.llm_controller_run(env)
            agent_a = action.LlmAgent_action_module(env)
            fixture_actions = agent_a.llm_controller_run(
                env, negotiation_text, conflicting_info, env.controlled_vehicles, None
            )
            report["parsed_fixture_actions"] = json_value(fixture_actions)

        # No env.step: fixtures are never applied to the simulated traffic.
        report["environment_steps"] = env.steps
        report["after_prompt_build_vehicles"] = [vehicle_state(v) for v in vehicles]
        if env.steps != 0:
            raise RuntimeError("Capture unexpectedly advanced the simulation")
        if len(report["calls"]) != 1 + len(vehicles):
            raise RuntimeError("Unexpected number of captured calls")
        if "llm_controller.memory" in sys.modules:
            raise RuntimeError("Memory module was unexpectedly imported")
        report["memory_module_imported"] = False
        report["status"] = "captured"
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "prompt-capture")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8] + ".json"
    output = args.output_dir / name
    report = {
        "mode": "offline_original_prompt_capture",
        "git_commit": git_revision(), "python_executable": sys.executable,
        "seed": args.seed, "status": "running", "calls": [],
        "llm_enabled": False, "memory_enabled": False,
        "limitation": "Action prompts depend on an arbitrary negotiation fixture, not an actual LLM answer. Original speed clamp and parsers run, but env.step is never called. Tokens are not measured.",
    }
    console = io.StringIO()
    exit_code = 0
    try:
        with redirect_stdout(console):
            capture(args, report)
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
        exit_code = 1
    finally:
        report["original_console"] = console.getvalue()
        output.write_text(json.dumps(json_value(report), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        print("Status: " + report["status"])
        print("Captured calls: " + str(len(report["calls"])))
        print("Result: " + str(output.resolve()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
