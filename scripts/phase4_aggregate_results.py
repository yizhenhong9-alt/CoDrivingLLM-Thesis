import argparse
import json
import statistics
import sys
from pathlib import Path


SUPPORTED_SCHEMA = "phase4c.case.v1"
SUPPORTED_PROTOCOL = "phase4c-intersection-v1"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only Phase 4C intersection case aggregator")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--memory-mode", required=True, choices=["off", "on"])
    return parser.parse_args(argv)


def absolute_directory(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("input-root must be an absolute path")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("input-root must be a directory")
    return path


def load_cases(root, memory_mode):
    paths = sorted(root.rglob("case.json"))
    if not paths:
        raise RuntimeError("No case.json artifacts were discovered")
    cases = []
    incomplete = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("scenario") != "intersection":
            raise RuntimeError("Unsupported scenario artifact: {}".format(path))
        if data.get("schema_version") != SUPPORTED_SCHEMA:
            raise RuntimeError("Incompatible schema version in {}".format(path))
        if data.get("protocol_version") != SUPPORTED_PROTOCOL:
            raise RuntimeError("Incompatible protocol version in {}".format(path))
        if data.get("memory_mode") != memory_mode:
            continue
        if data.get("artifact_complete") is not True:
            incomplete.append(str(path))
            continue
        if data.get("status") not in {"completed", "failed"}:
            raise RuntimeError("Unknown completed case status in {}".format(path))
        cases.append((path, data))
    if incomplete:
        raise RuntimeError(
            "Incomplete matching case artifacts found; refusing silent omission: {}".format(
                incomplete))
    if not cases:
        raise RuntimeError("No completed matching cases were discovered")
    return cases


def describe(values):
    if not values:
        return {"count": 0, "mean": None, "median": None}
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def aggregate(cases, memory_mode):
    seeds = [data["seed"]["requested"] for _, data in cases]
    duplicate_seeds = sorted({seed for seed in seeds if seeds.count(seed) > 1})
    if duplicate_seeds:
        raise RuntimeError(
            "Multiple completed cases found for the same seed and Memory mode: {}"
            .format(duplicate_seeds))

    successful = [data for _, data in cases if data.get("success") is True]
    failed = [data for _, data in cases if data.get("success") is not True]
    categories = {}
    for data in failed:
        if data.get("status") == "failed":
            category = (data.get("failure") or {}).get("category", "unclassified")
        else:
            category = "completed_unsuccessful_{}".format(
                data.get("terminal_reason") or "unknown")
        categories[category] = categories.get(category, 0) + 1

    def episode_values(key):
        return [
            data["episode"][key] for _, data in cases
            if isinstance(data.get("episode", {}).get(key), (int, float))
        ]

    return {
        "schema_version": "phase4c.aggregate.v1",
        "source_schema_version": SUPPORTED_SCHEMA,
        "protocol_version": SUPPORTED_PROTOCOL,
        "scenario": "intersection",
        "memory_mode": memory_mode,
        "total_discovered_cases": len(cases),
        "successful_cases": len(successful),
        "failed_cases": len(failed),
        "failure_categories": categories,
        "success_rate": len(successful) / len(cases),
        "seeds_included": sorted(seeds),
        "episode_steps": describe(episode_values("steps")),
        "simulation_time_seconds": describe(
            episode_values("simulation_time_seconds")),
        "wall_clock_runtime_seconds": describe(
            episode_values("wall_clock_runtime_seconds")),
        "llm_calls_per_case": describe([
            data.get("counters", {}).get("llm_calls", 0) for _, data in cases
        ]),
        "case_artifacts": [str(path) for path, _ in cases],
        "pet": "not calculated in Phase 4C",
    }


def main(argv=None):
    args = parse_args(argv)
    root = absolute_directory(args.input_root)
    result = aggregate(load_cases(root, args.memory_mode), args.memory_mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
