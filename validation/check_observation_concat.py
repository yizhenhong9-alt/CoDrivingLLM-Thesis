"""Compare public DataFrame.append with concat; requires pandas 1.3.5."""

import argparse
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
import traceback
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smoke_intersection import git_revision, json_value


def compare(pd, np, left, right):
    pd.testing.assert_frame_equal(left, right, check_exact=True, check_dtype=True)
    a, b = left.values.copy(), right.values.copy()
    if a.dtype != b.dtype or a.shape != b.shape:
        raise AssertionError("Final ndarray dtype or shape differs")
    np.testing.assert_array_equal(a, b)


def verify(report, seeds, max_steps):
    import gym
    import highway_env
    import numpy as np
    import pandas as pd
    import highway_env.envs.common.observation as observation

    report["versions"] = {
        "pandas": pd.__version__, "numpy": np.__version__, "gym": gym.__version__,
    }
    if pd.__version__ != "1.3.5":
        raise RuntimeError("Run in the confirmed pandas 1.3.5 environment; do not change packages")
    if Path(highway_env.__file__).resolve().parent != ROOT / "highway_env":
        raise RuntimeError("Loaded highway_env is not the repository copy")
    report["environment_source"] = str(Path(highway_env.__file__).resolve())

    # Synthetic cases cover no neighbours, partial occupancy and full occupancy.
    features = ["presence", "x", "y", "vx", "vy"]
    for count in range(5):
        ego = pd.DataFrame([[1, 2.0, 45.0, 0.0, -5.0]], columns=features)
        nearby = pd.DataFrame(
            [[1, float(i + 1), -3.5, 0.25, -1.0] for i in range(count)],
            columns=features,
        )
        old, new = ego.copy(), ego.copy()
        if count:
            old = old.append(nearby, ignore_index=True)
            new = pd.concat([new, nearby], ignore_index=True)
        if len(old) < 5:
            padding = pd.DataFrame(np.zeros((5 - len(old), 5)), columns=features)
            old = old.append(padding, ignore_index=True)
            new = pd.concat([new, padding], ignore_index=True)
        compare(pd, np, old[features], new[features])
        report["synthetic_cases"].append({"neighbours": count, "passed": True})

    # Execute the current observe body with only its return instrumented to expose
    # the intermediate DataFrame. Build explicit concat and append variants,
    # accepting either production implementation. Never patch the installed class.
    source = textwrap.dedent(inspect.getsource(observation.KinematicObservation.observe))
    replacements = [
        ("df = pd.concat([df, nearby], ignore_index=True)",
         "df = df.append(nearby, ignore_index=True)"),
        ("df = pd.concat([df, pd.DataFrame(data=rows, columns=self.features)], ignore_index=True)",
         "df = df.append(pd.DataFrame(data=rows, columns=self.features), ignore_index=True)"),
    ]
    if source.count("return obs") != 1:
        raise RuntimeError("Observation source changed; review test instrumentation")
    current_source = source.replace("return obs", "return df, obs")
    legacy_source = current_source
    for before, after in replacements:
        if current_source.count(before) + current_source.count(after) != 1:
            raise RuntimeError("Observation merge source changed; review test baseline")
        current_source = current_source.replace(after, before)
        legacy_source = legacy_source.replace(before, after)
    report["production_merge_method"] = "concat" if "pd.concat(" in source else "append"
    report["observation_source_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    functions = []
    for code in (current_source, legacy_source):
        namespace = dict(vars(observation))
        exec(compile(code, "<observation-equivalence>", "exec"), namespace)
        functions.append(namespace["observe"])
    current, legacy = functions

    for seed in seeds:
        env = gym.make("intersection-multi-agent-v0")
        try:
            env.reset(is_training=False, testing_seeds=seed)
            for step in range(max_steps + 1):
                for index, observer in enumerate(env.observation_type.agents_observation_types):
                    if observer.order != "sorted":
                        raise RuntimeError("Expected deterministic sorted observations")
                    new_df, new_obs = current(observer)
                    old_df, old_obs = legacy(observer)
                    compare(pd, np, old_df, new_df)
                    if old_obs.dtype != new_obs.dtype:
                        raise AssertionError("Returned observation dtype differs")
                    np.testing.assert_array_equal(old_obs, new_obs)
                    report["live_cases"].append({
                        "seed": seed, "step": step, "observer_index": index,
                        "vehicle_id": observer.observer_vehicle.id,
                        "shape": list(new_obs.shape),
                        "dtypes": [str(dtype) for dtype in new_df.dtypes],
                        "passed": True,
                    })
                if step == max_steps:
                    break
                actions = tuple(
                    agent.actions_indexes["IDLE"]
                    for agent in env.action_type.agents_action_types
                )
                _, _, done, _ = env.step(actions, env)
                if done:
                    raise RuntimeError("Environment terminated before all requested checkpoints")
        finally:
            env.close()
    report["status"] = "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 42])
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "concat-equivalence")
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8] + ".json"
    output = args.output_dir / name
    report = {
        "mode": "append_concat_equivalence", "git_commit": git_revision(),
        "python_executable": sys.executable, "python": sys.version,
        "baseline": "Public append hypothesis, not the unavailable _append method",
        "llm_enabled": False, "memory_enabled": False,
        "seeds": args.seeds, "max_steps": args.max_steps,
        "synthetic_cases": [], "live_cases": [], "status": "running",
    }
    exit_code = 0
    try:
        verify(report, args.seeds, args.max_steps)
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
        exit_code = 1
    finally:
        output.write_text(json.dumps(json_value(report), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        print("Status: " + report["status"])
        print("Synthetic cases passed: " + str(len(report["synthetic_cases"])))
        print("Live observation cases passed: " + str(len(report["live_cases"])))
        print("Result: " + str(output.resolve()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
