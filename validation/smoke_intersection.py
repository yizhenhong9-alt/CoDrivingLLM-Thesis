"""Exercise the local intersection simulator without LLM or memory imports."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
# Direct execution sets sys.path[0] to validation/, not the repository root.
# Prefer the author's local simulator over any installed highway-env package.
sys.path.insert(0, str(ROOT))


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--action", choices=("IDLE", "FASTER", "SLOWER"), default="IDLE")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "intersection-smoke")
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")
    return args


def json_value(value):
    """Convert simulator values without importing NumPy at module import time."""
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    return value


def vehicle_state(vehicle):
    return json_value({
        "id": vehicle.id,
        "position": vehicle.position,
        "heading_rad": vehicle.heading,
        "speed_mps": vehicle.speed,
        "speed_index": vehicle.speed_index,
        "target_speed_mps": vehicle.target_speed,
        "lane_index": vehicle.lane_index,
        "target_lane_index": vehicle.target_lane_index,
        "route": vehicle.route,
        "crashed": vehicle.crashed,
        "low_level_action": dict(vehicle.action),
    })


def git_revision():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(args, report):
    # These imports register the repository's environments, but never import
    # Run_multi_CAV_LLM or llm_controller (and thus never initialize memory).
    import gym
    import highway_env
    import numpy as np
    import pandas as pd

    source = Path(highway_env.__file__).resolve()
    if source.parent != ROOT / "highway_env":
        raise RuntimeError("Expected repository highway_env, loaded: " + str(source))
    report["environment_source"] = str(source)
    report["versions"] = {
        "gym": gym.__version__, "numpy": np.__version__, "pandas": pd.__version__,
    }

    env = gym.make("intersection-multi-agent-v0")
    try:
        # Construction already resets once. Explicit testing reset selects
        # the requested seed independently of the internal seed counter.
        obs = env.reset(is_training=False, testing_seeds=args.seed)
        report["config"] = json_value(env.config)
        report["observation_shape"] = list(obs.shape)
        report["initial_vehicles"] = [vehicle_state(v) for v in env.controlled_vehicles]
        report["initial_road_vehicle_count"] = len(env.road.vehicles)
        agents = env.action_type.agents_action_types
        report["action_mappings"] = [json_value(agent.actions) for agent in agents]
        report["declared_action_space"] = str(env.action_space)
        for index in range(args.max_steps):
            if len(agents) != len(env.controlled_vehicles):
                raise RuntimeError("Controlled vehicle and action controller counts differ")
            actions = tuple(agent.actions_indexes[args.action] for agent in agents)
            for action, agent in zip(actions, agents):
                if action not in agent.actions:
                    raise RuntimeError("Action is absent from execution mapping")
            before_ticks = env.time
            started = time.perf_counter()
            obs, reward, done, info = env.step(actions, env)
            elapsed = time.perf_counter() - started
            report["steps"].append(json_value({
                "step": index + 1,
                "action_name": args.action,
                "actions": actions,
                "wall_seconds": elapsed,
                "physics_ticks": env.time - before_ticks,
                "simulated_seconds": (env.time - before_ticks) / env.config["simulation_frequency"],
                "reward": reward,
                "environment_done": bool(done),
                "info": info,
                "vehicles": [vehicle_state(v) for v in env.controlled_vehicles],
            }))
            if done:
                report["stop_reason"] = "environment_done"
                break
        else:
            report["stop_reason"] = "max_steps"
        report["status"] = "completed"
    finally:
        env.close()


def main():
    args = arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir / (stamp + "-" + uuid4().hex[:8] + ".json")
    report = {
        "mode": "fixed_action_environment_smoke_test",
        "llm_enabled": False,
        "memory_enabled": False,
        "note": "No LLM decisions or LLM-module speed clamp; not a driving performance experiment.",
        "git_commit": git_revision(),
        "python": sys.version,
        "python_executable": sys.executable,
        "seed": args.seed,
        "max_steps": args.max_steps,
        "fixed_action": args.action,
        "status": "running",
        "steps": [],
    }
    exit_code = 0
    try:
        run(args, report)
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
        exit_code = 1
    finally:
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        print("Result: " + str(output.resolve()))
        print("Status: " + report["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
