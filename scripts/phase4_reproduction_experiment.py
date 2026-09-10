import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request


SCHEMA_VERSION = "phase4c.case.v1"
SCENARIOS = {
    "intersection": {
        "environment_id": "intersection-multi-agent-v0",
        "protocol_version": "phase4c-intersection-v1",
        "config": None,
        "controlled_vehicle_count": 4,
        "decision_speed_limit": 5,
    },
    "merge": {
        "environment_id": "merge-multi-agent-v0",
        "protocol_version": "phase5b-merge-smoke-v1",
        "config": {
            "simulation_frequency": 20,
            "policy_frequency": 5,
            "duration": 40,
        },
        "controlled_vehicle_count": 3,
        "decision_speed_limit": 20,
    },
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MEMORY_SECTION_PREFIX = (
    "Here is your action when scenarios are similar to the current scenario in the past, "
    "you should learn from past memory try not to take the cation that cause more danger:\n"
)
MEMORY_SECTION_SUFFIX = (
    "\n\nBased on the planning trajectory, you have the following conflicts with other vehicles."
)
KNOWN_DATABASE_ROOTS = (
    REPOSITORY_ROOT / "db",
    REPOSITORY_ROOT / "llm_controller" / "chroma",
)
RELEVANT_PACKAGES = (
    "gym", "numpy", "pandas", "langchain", "chromadb", "tokenizers", "posthog"
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run exactly one controlled reproduction case")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--memory-mode", required=True, choices=["off", "on"])
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11435")
    parser.add_argument("--chat-model", default="qwen2.5:7b")
    parser.add_argument("--embedding-model", default="nomic-embed-text:latest")
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args(argv)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    return str(value)


def canonical_json(value):
    return json.dumps(
        json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("{} must be an absolute path".format(label))
    return path.resolve(strict=False)


def is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_run_id(run_id):
    if not run_id or run_id in {".", ".."}:
        raise ValueError("run-id must be non-empty and directory-safe")
    if any(character in run_id for character in '<>:"/\\|?*'):
        raise ValueError("run-id contains a Windows-invalid path character")


def build_paths(args):
    output_root = absolute_path(args.output_root, "output root")
    validate_run_id(args.run_id)
    mode_directory = "memory_{}".format(args.memory_mode)
    run_directory = (
        output_root / args.scenario / mode_directory /
        "seed_{}".format(args.seed) / args.run_id
    ).resolve(strict=False)
    if not is_within(run_directory, output_root) or run_directory == output_root:
        raise ValueError("run directory must be strictly inside output root")
    if run_directory.exists():
        raise FileExistsError("run directory already exists; refusing overwrite")

    paths = {
        "output_root": output_root,
        "run_directory": run_directory,
        "case": run_directory / "case.json",
        "trajectory": run_directory / "trajectory.jsonl",
        "llm_calls": run_directory / "llm_calls.jsonl",
        "memory_events": (
            run_directory / "memory_events.jsonl"
            if args.memory_mode == "on" else None
        ),
        "database": run_directory / "chroma" if args.memory_mode == "on" else None,
    }
    if paths["database"] is not None:
        database = paths["database"].resolve(strict=False)
        if not is_within(database, run_directory) or database == run_directory:
            raise ValueError("Memory database must be inside the fresh run directory")
        for known_value in KNOWN_DATABASE_ROOTS:
            known = known_value.resolve(strict=False)
            if database == known or is_within(database, known):
                raise ValueError("Memory database overlaps an original/historical root")
    return paths


def atomic_write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(json_safe(value), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def append_jsonl(path, value):
    if path is None:
        return
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(json_safe(value), ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def git_value(*arguments):
    completed = subprocess.run(
        ["git", "-c", "safe.directory={}".format(REPOSITORY_ROOT)] + list(arguments),
        cwd=str(REPOSITORY_ROOT), capture_output=True, text=True, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def read_json(url, timeout):
    with request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_model(tags_response, requested_model):
    models = tags_response.get("models") if isinstance(tags_response, dict) else None
    if not isinstance(models, list):
        raise ValueError("Ollama tags response is missing models")
    matches = [
        item for item in models
        if isinstance(item, dict)
        and requested_model in {item.get("name"), item.get("model")}
    ]
    if len(matches) != 1:
        raise ValueError("Requested model did not resolve uniquely: {}".format(
            requested_model))
    if not isinstance(matches[0].get("digest"), str) or not matches[0]["digest"]:
        raise ValueError("Resolved model is missing a digest")
    return matches[0]


def model_inventory(endpoint, timeout, chat_model, embedding_model, memory_mode):
    base = endpoint.rstrip("/")
    version = read_json(base + "/api/version", timeout)
    tags = read_json(base + "/api/tags", timeout)
    result = {
        "version_response": version,
        "chat_model": resolve_model(tags, chat_model),
    }
    if memory_mode == "on":
        result["embedding_model"] = resolve_model(tags, embedding_model)
    return result


def vehicle_identifier(vehicle):
    return str(vehicle).split(":")[0].strip()


def route_value(vehicle):
    route = getattr(vehicle, "route", None)
    return json_safe(route) if route is not None else None


def arrival_value(env, vehicle):
    if not hasattr(env, "has_arrived"):
        return None
    try:
        return bool(env.has_arrived(vehicle))
    except Exception:
        return None


def vehicle_state(env, vehicle, vehicle_index):
    controlled = vehicle in env.controlled_vehicles
    controlled_index = (
        env.controlled_vehicles.index(vehicle) if controlled else None)
    position = getattr(vehicle, "position", None)
    return {
        "vehicle_index": vehicle_index,
        "simulator_id": json_safe(getattr(vehicle, "id", None)),
        "vehicle_identifier": vehicle_identifier(vehicle),
        "vehicle_class": type(vehicle).__name__,
        "controlled": controlled,
        "controlled_index": controlled_index,
        "x": float(position[0]) if position is not None else None,
        "y": float(position[1]) if position is not None else None,
        "speed": float(vehicle.speed),
        "heading": float(vehicle.heading),
        "lane_index": json_safe(getattr(vehicle, "lane_index", None)),
        "route": route_value(vehicle),
        "destination": json_safe(getattr(vehicle, "destination", None)),
        "crashed": bool(vehicle.crashed),
        "arrived": arrival_value(env, vehicle),
    }


def environment_snapshot(env):
    return [
        vehicle_state(env, vehicle, index)
        for index, vehicle in enumerate(env.road.vehicles)
    ]


def stable_initial_state(states):
    excluded = {"vehicle_identifier"}
    return [
        {key: value for key, value in state.items() if key not in excluded}
        for state in states
    ]


def log_policy_snapshot(path, env, sample_kind, policy_step, actions=None):
    action_by_index = actions or {}
    simulation_time = env.time / env.config["simulation_frequency"]
    for index, vehicle in enumerate(env.road.vehicles):
        state = vehicle_state(env, vehicle, index)
        controlled_index = state["controlled_index"]
        selected = action_by_index.get(controlled_index)
        append_jsonl(path, {
            "schema_version": SCHEMA_VERSION,
            "timestamp_utc": utc_now(),
            "sample_kind": sample_kind,
            "policy_step": policy_step,
            "simulation_substep": env.time,
            "simulation_time_seconds": simulation_time,
            "vehicle": state,
            "semantic_action": (
                selected.get("semantic_action") if selected else None),
            "action_id": selected.get("action_id") if selected else None,
        })


def log_recent_simulation_substeps(path, env, policy_step, actions):
    substeps = int(
        env.config["simulation_frequency"] // env.config["policy_frequency"])
    end_substep = env.time
    for vehicle_index, vehicle in enumerate(env.road.vehicles):
        history = list(getattr(vehicle, "history", []))[:substeps]
        history.reverse()
        controlled = vehicle in env.controlled_vehicles
        controlled_index = (
            env.controlled_vehicles.index(vehicle) if controlled else None)
        selected = actions.get(controlled_index)
        for offset, historical in enumerate(history):
            simulation_substep = end_substep - len(history) + offset + 1
            append_jsonl(path, {
                "schema_version": SCHEMA_VERSION,
                "timestamp_utc": utc_now(),
                "sample_kind": "simulation_substep",
                "policy_step": policy_step,
                "simulation_substep": simulation_substep,
                "simulation_time_seconds": (
                    simulation_substep / env.config["simulation_frequency"]),
                "vehicle": {
                    "vehicle_index": vehicle_index,
                    "simulator_id": json_safe(getattr(vehicle, "id", None)),
                    "vehicle_identifier": vehicle_identifier(vehicle),
                    "vehicle_class": type(vehicle).__name__,
                    "controlled": controlled,
                    "controlled_index": controlled_index,
                    "x": float(historical.position[0]),
                    "y": float(historical.position[1]),
                    "speed": float(historical.speed),
                    "heading": float(historical.heading),
                    "lane_index": json_safe(getattr(historical, "lane_index", None)),
                    "route": route_value(vehicle),
                    "destination": json_safe(getattr(vehicle, "destination", None)),
                    "crashed": bool(vehicle.crashed),
                    "arrived": arrival_value(env, vehicle),
                },
                "semantic_action": (
                    selected.get("semantic_action") if selected else None),
                "action_id": selected.get("action_id") if selected else None,
            })


def extract_memory_section(prompt):
    start = prompt.find(MEMORY_SECTION_PREFIX)
    if start < 0:
        return None
    start += len(MEMORY_SECTION_PREFIX)
    end = prompt.find(MEMORY_SECTION_SUFFIX, start)
    return None if end < 0 else prompt[start:end]


def memory_count(memory):
    return len(memory.scenario_memory._collection.get(
        include=["embeddings"])["embeddings"])


def new_memory(env, args, database_path):
    from llm_controller.memory import DrivingMemory
    return DrivingMemory(
        env,
        embedding_backend="ollama",
        embedding_config={
            "endpoint": args.ollama_endpoint,
            "model": args.embedding_model,
            "timeout": args.timeout,
        },
        persist_directory=str(database_path),
    )


def backend_record(backend, phase, success, parsed=None, identity=None,
                   error=None, parser_success=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": utc_now(),
        "phase": phase,
        "identity": identity,
        "backend": backend.backend,
        "model": backend.model,
        "endpoint": backend.endpoint,
        "request_messages": backend.last_messages,
        "raw_response": backend.last_raw_response,
        "raw_content": backend.last_content,
        "parsed_result": parsed,
        "latency_seconds": backend.last_latency_seconds,
        "success": success and parser_success is not False,
        "transport_success": success,
        "parser_success": parser_success,
        "error": error,
        "retry_index": 0,
        "sampling_parameters": "provider defaults; LLM nondeterministic",
    }


def terminal_reason(env, scenario):
    if any(vehicle.crashed for vehicle in env.controlled_vehicles):
        return "controlled_vehicle_crash"
    if scenario == "merge":
        if env.steps >= env.config["duration"] * env.config["policy_frequency"]:
            return "duration_limit"
        return "unknown_terminal_condition"
    arrivals = [arrival_value(env, vehicle) for vehicle in env.controlled_vehicles]
    if arrivals and all(value is True for value in arrivals):
        return "all_controlled_vehicles_arrived"
    if env.steps >= env.config["duration"] * env.config["policy_frequency"] - 1:
        return "duration_limit"
    if env.config.get("offroad_terminal") and not env.vehicle.on_road:
        return "offroad"
    return "unknown_terminal_condition"


def evaluate_intersection_success(env):
    crashed = [bool(vehicle.crashed) for vehicle in env.controlled_vehicles]
    arrived = [arrival_value(env, vehicle) for vehicle in env.controlled_vehicles]
    if not arrived or any(value is None for value in arrived):
        raise RuntimeError("Intersection arrival predicate could not be evaluated")
    completed = list(arrived)
    success = not any(crashed) and all(completed) and all(arrived)
    return {
        "success": bool(success),
        "per_cav_crashed": crashed,
        "per_cav_task_completed": completed,
        "per_cav_arrived": arrived,
    }


def serialize_conflicts(conflicting_info):
    return [
        {
            key: vehicle_identifier(value) if key in {"vehicle_i", "vehicle_j"}
            else json_safe(value)
            for key, value in item.items()
        }
        for item in conflicting_info
    ]


def classify_failure(stage):
    for prefix, category in (
        ("negotiation backend", "backend"),
        ("decision backend", "backend"),
        ("negotiation parser", "parser"),
        ("decision parser", "parser"),
        ("memory", "memory"),
        ("simulator", "simulator"),
        ("success evaluation", "success_evaluation"),
        ("environment", "infrastructure"),
        ("Ollama", "backend"),
    ):
        if stage.startswith(prefix):
            return category
    return "infrastructure"


def run_case(args, paths, case, state):
    import gym
    import highway_env
    from llm_controller.llm_agent_action import LlmAgent_action_module
    from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module

    case["failure_stage"] = "runtime provenance"
    head = git_value("rev-parse", "HEAD")
    dirty = git_value("status", "--short")
    if head is None or dirty is None:
        raise RuntimeError("Git identity/status could not be resolved")
    case["git"] = {"commit": head, "dirty": bool(dirty), "status_short": dirty}
    case["runtime"] = {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "conda_prefix": os.environ.get("CONDA_PREFIX"),
        "highway_env_path": str(Path(highway_env.__file__).resolve()),
        "package_versions": {
            name: package_version(name) for name in RELEVANT_PACKAGES
        },
    }
    expected_highway_root = (REPOSITORY_ROOT / "highway_env").resolve()
    imported_highway = Path(highway_env.__file__).resolve()
    if not is_within(imported_highway, expected_highway_root):
        raise RuntimeError("Repository-local highway_env is not active")
    atomic_write_json(paths["case"], case)

    case["failure_stage"] = "Ollama inventory"
    inventory = model_inventory(
        args.ollama_endpoint, args.timeout, args.chat_model,
        args.embedding_model, args.memory_mode)
    case["ollama"]["version_response"] = inventory["version_response"]
    case["ollama"]["resolved_chat_model"] = inventory["chat_model"]
    if args.memory_mode == "on":
        case["memory"]["resolved_embedding_model"] = inventory["embedding_model"]
    atomic_write_json(paths["case"], case)

    scenario_contract = SCENARIOS[args.scenario]
    environment_id = scenario_contract["environment_id"]
    case["failure_stage"] = "environment initialization and explicit seed reset"
    if scenario_contract["config"] is None:
        env = gym.make(environment_id)
    else:
        env = gym.make(environment_id, config=dict(scenario_contract["config"]))
    state["env"] = env
    observation = env.reset(is_training=False, testing_seeds=args.seed)
    initial_states = environment_snapshot(env)
    stable_states = stable_initial_state(initial_states)
    initial_hash = sha256_json({
        "scenario": args.scenario,
        "environment_id": environment_id,
        "effective_config": json_safe(env.config),
        "vehicles": stable_states,
    })
    case["seed"] = {
        "requested": args.seed,
        "effective": args.seed,
        "reset_call": "env.reset(is_training=False, testing_seeds={})".format(
            args.seed),
        "python_random_policy": "random.seed(testing_seeds) in AbstractEnv.reset",
        "numpy_random_policy": "numpy.random.seed(testing_seeds) in AbstractEnv.reset",
        "llm_determinism": "not guaranteed; Ollama/provider-default sampling is separate",
    }
    case["environment"] = {
        "id": env.spec.id,
        "effective_config": json_safe(env.config),
        "controlled_cav_count": len(env.controlled_vehicles),
        "road_vehicle_count": len(env.road.vehicles),
        "observation_type": type(observation).__name__,
        "observation_shape": json_safe(getattr(observation, "shape", None)),
        "action_space": str(env.action_space),
        "initial_vehicle_states": initial_states,
        "initial_state_hash_basis": "all stable fields except process-global display identifier",
        "initial_state_sha256": initial_hash,
    }
    case["initial_state_sha256"] = initial_hash
    expected_controlled = scenario_contract["controlled_vehicle_count"]
    if len(env.controlled_vehicles) != expected_controlled:
        raise RuntimeError(
            "{} reproduction requires exactly {} controlled CAVs".format(
                args.scenario.capitalize(), expected_controlled))
    log_policy_snapshot(paths["trajectory"], env, "initial", 0)
    atomic_write_json(paths["case"], case)

    if args.memory_mode == "on":
        case["failure_stage"] = "memory initialization"
        initial_memory = new_memory(env, args, paths["database"])
        initial_count = memory_count(initial_memory)
        case["memory"]["initial_count"] = initial_count
        if initial_count != 0:
            raise RuntimeError("Independent-episode Memory database is not empty")
        append_jsonl(paths["memory_events"], {
            "timestamp_utc": utc_now(), "event": "initialize",
            "count": initial_count, "database_path": str(paths["database"]),
        })
        del initial_memory
        gc.collect()

    negotiation_agent = LlmAgent_negotiation_module(
        env, backend="ollama", model=args.chat_model,
        endpoint=args.ollama_endpoint, timeout=args.timeout)
    action_agent = LlmAgent_action_module(
        env, backend="ollama", model=args.chat_model,
        endpoint=args.ollama_endpoint, timeout=args.timeout,
        memory_mode=args.memory_mode)

    terminal = False
    while not terminal:
        policy_step = case["episode"]["steps"]
        memory = None
        if args.memory_mode == "on":
            case["failure_stage"] = "memory reopen at policy step {}".format(policy_step)
            memory = new_memory(env, args, paths["database"])

        case["failure_stage"] = "negotiation backend at policy step {}".format(
            policy_step)
        case["counters"]["llm_calls"] += 1
        case["counters"]["negotiation_calls"] += 1
        try:
            negotiation_content, conflicting_info = (
                negotiation_agent.llm_controller_run(env))
        except Exception as error:
            append_jsonl(paths["llm_calls"], backend_record(
                negotiation_agent.chat_backend, "negotiation", False,
                error={"type": type(error).__name__, "message": str(error)}))
            raise

        parsed_by_vehicle = {}
        parsed_pairs = set()
        negotiation_participants = (
            env.controlled_vehicles
            if args.scenario == "intersection" else env.road.vehicles
        )
        for vehicle in negotiation_participants:
            identifier = vehicle_identifier(vehicle)
            parsed = action_agent.extract_vehicle_conflicts(
                negotiation_content, identifier)
            parsed_by_vehicle[identifier] = parsed
            parsed_pairs.update((first, second) for first, second, _ in parsed)
        expected_pairs = {
            (vehicle_identifier(item["vehicle_i"]),
             vehicle_identifier(item["vehicle_j"]))
            for item in conflicting_info
        }
        expected_bidirectional = expected_pairs | {
            (second, first) for first, second in expected_pairs
        }
        parsed_bidirectional = parsed_pairs | {
            (second, first) for first, second in parsed_pairs
        }
        negotiation_parsed = {
            "by_vehicle": parsed_by_vehicle,
            "conflicts": serialize_conflicts(conflicting_info),
            "expected_pair_count": len(expected_pairs),
            "parsed_pair_count": len(parsed_pairs),
        }
        negotiation_parser_success = (
            not expected_pairs
            or expected_bidirectional.issubset(parsed_bidirectional)
        )
        append_jsonl(paths["llm_calls"], backend_record(
            negotiation_agent.chat_backend, "negotiation", True,
            parsed=negotiation_parsed,
            identity={"policy_step": policy_step},
            parser_success=negotiation_parser_success))
        if not negotiation_parser_success:
            case["failure_stage"] = "negotiation parser at policy step {}".format(
                policy_step)
            case["counters"]["parser_failures"] += 1
            case["counters"]["negotiation_parser_failures"] += 1
            raise RuntimeError("Negotiation parser did not cover every conflict pair")

        action_ids = []
        action_records = {}
        for cav_index, ego_vehicle in enumerate(env.controlled_vehicles):
            speed_limit = scenario_contract["decision_speed_limit"]
            ego_vehicle.speed = (
                speed_limit if ego_vehicle.speed > speed_limit else ego_vehicle.speed)
            negotiation_results = (
                action_agent.transfer_negotiation_prompts_to_results(
                    ego_vehicle, negotiation_content))
            scenario = action_agent.prompt_engineer(
                ego_vehicle, env.road, env, negotiation_results, conflicting_info)
            case["failure_stage"] = (
                "decision backend at policy step {}, CAV {}".format(
                    policy_step, cav_index))
            case["counters"]["llm_calls"] += 1
            case["counters"]["decision_calls"] += 1
            try:
                llm_action = action_agent.send_to_chatgpt(
                    ego_vehicle, scenario, negotiation_results, memory)
            except Exception as error:
                append_jsonl(paths["llm_calls"], backend_record(
                    action_agent.chat_backend, "decision", False,
                    identity={"policy_step": policy_step, "cav_index": cav_index,
                              "vehicle": vehicle_identifier(ego_vehicle)},
                    error={"type": type(error).__name__, "message": str(error)}))
                raise

            semantic_action = action_agent.extract_decision(
                action_agent.chat_backend.last_content)
            action_id = int(llm_action[0])
            parsed_decision = {
                "semantic_action": semantic_action,
                "action_id": action_id,
                "negotiation_results": negotiation_results,
                "scenario": scenario,
            }
            decision_parser_success = (
                semantic_action in action_agent.ACTIONS_ALL.values()
                and action_id in action_agent.ACTIONS_ALL
            )
            append_jsonl(paths["llm_calls"], backend_record(
                action_agent.chat_backend, "decision", True,
                parsed=parsed_decision,
                identity={"policy_step": policy_step, "cav_index": cav_index,
                          "vehicle": vehicle_identifier(ego_vehicle)},
                parser_success=decision_parser_success))

            if semantic_action not in action_agent.ACTIONS_ALL.values():
                case["failure_stage"] = (
                    "decision parser at policy step {}, CAV {}".format(
                        policy_step, cav_index))
                case["counters"]["parser_failures"] += 1
                case["counters"]["decision_parser_failures"] += 1
                raise RuntimeError("Decision parser returned an invalid action")
            if action_id not in action_agent.ACTIONS_ALL:
                case["failure_stage"] = (
                    "decision parser at policy step {}, CAV {}".format(
                        policy_step, cav_index))
                case["counters"]["parser_failures"] += 1
                case["counters"]["decision_parser_failures"] += 1
                raise RuntimeError("Decision mapping returned an invalid action ID")

            action_records[cav_index] = {
                "semantic_action": semantic_action, "action_id": action_id,
            }
            action_ids.append(action_id)

            if args.memory_mode == "on":
                case["failure_stage"] = (
                    "memory retrieval validation at policy step {}, CAV {}".format(
                        policy_step, cav_index))
                retrieved = memory.last_retrieval_results
                formatted = action_agent.format_relative_memory(retrieved)
                prompt = action_agent.chat_backend.last_messages[0]["content"]
                extracted = extract_memory_section(prompt)
                expected_query = "\n".join(scenario.strip().split("\n")[-2:])
                event = {
                    "timestamp_utc": utc_now(), "event": "retrieval",
                    "policy_step": policy_step, "cav_index": cav_index,
                    "vehicle": vehicle_identifier(ego_vehicle),
                    "query": memory.last_retrieval_query,
                    "query_matches_original": (
                        memory.last_retrieval_query == expected_query),
                    "top_k": memory.last_retrieval_top_k,
                    "retrieved_count": len(retrieved),
                    "retrieved_metadata": retrieved,
                    "retrieval_scores": memory.last_retrieval_scores,
                    "prompt_memory_exact_match": extracted == formatted,
                }
                append_jsonl(paths["memory_events"], event)
                case["memory"]["retrieval_count"] += 1
                case["memory"]["retrieved_experiences"] += len(retrieved)
                if (not event["query_matches_original"] or event["top_k"] != 2
                        or not event["prompt_memory_exact_match"]):
                    raise RuntimeError("Memory retrieval/prompt semantics validation failed")

                count_before = memory_count(memory)
                case["failure_stage"] = (
                    "memory update at policy step {}, CAV {}".format(
                        policy_step, cav_index))
                case["memory"]["update_count"] += 1
                action_agent.memory_update(memory, scenario, llm_action)
                count_after = memory_count(memory)
                write_success = count_after == count_before + 1
                append_jsonl(paths["memory_events"], {
                    "timestamp_utc": utc_now(), "event": "update",
                    "policy_step": policy_step, "cav_index": cav_index,
                    "vehicle": vehicle_identifier(ego_vehicle),
                    "count_before": count_before, "count_after": count_after,
                    "successful_write": write_success,
                    "page_content": memory.last_added_page_content,
                    "metadata": memory.last_added_metadata,
                    "timing": "after decision and before env.step",
                })
                if not write_success:
                    raise RuntimeError("Memory write did not increase count by one")
                case["memory"]["successful_write_count"] += 1

            atomic_write_json(paths["case"], case)

        joint_action = tuple(action_ids)
        executable_maps = [
            action_type.actions
            for action_type in env.action_type.agents_action_types
        ]
        declared_action_space_contains = env.action_space.contains(joint_action)
        if not declared_action_space_contains:
            case["counters"]["declared_action_space_mismatch_steps"] += 1
        if not all(
                action_id in action_map
                for action_id, action_map in zip(joint_action, executable_maps)):
            case["failure_stage"] = "simulator action validation at policy step {}".format(
                policy_step)
            raise RuntimeError("Joint action is unsupported by executable maps")

        case["failure_stage"] = "simulator env.step at policy step {}".format(
            policy_step)
        observation, reward, terminal, info = env.step(joint_action, env)
        reward_value = float(reward)
        case["episode"]["steps"] += 1
        case["episode"]["total_reward"] += reward_value
        case["episode"]["simulation_substeps"] = env.time
        case["episode"]["simulation_time_seconds"] = (
            env.time / env.config["simulation_frequency"])
        case["episode"]["last_info"] = json_safe(info)
        case["episode"]["last_joint_action"] = list(joint_action)
        case["episode"]["last_declared_action_space_contains"] = (
            declared_action_space_contains)
        case["episode"]["last_observation_shape"] = json_safe(
            getattr(observation, "shape", None))
        log_recent_simulation_substeps(
            paths["trajectory"], env, policy_step, action_records)
        log_policy_snapshot(
            paths["trajectory"], env, "policy_step_end",
            case["episode"]["steps"], action_records)
        atomic_write_json(paths["case"], case)
        if memory is not None:
            del memory
            gc.collect()

    case["failure_stage"] = "success evaluation"
    if args.scenario == "intersection":
        result = evaluate_intersection_success(env)
        case.update(result)
    else:
        case["evaluation"] = {
            "formal_success_evaluated": False,
            "classification": "reproduction diagnostic only",
            "reason": "Released Merge has no explicit case-level success rule; Phase 5B validates functional completion only",
            "per_cav_crashed": [
                bool(vehicle.crashed) for vehicle in env.controlled_vehicles],
            "per_cav_arrived_diagnostic": [
                arrival_value(env, vehicle) for vehicle in env.controlled_vehicles],
        }
    case["terminal_reason"] = terminal_reason(env, args.scenario)
    if case["terminal_reason"] == "unknown_terminal_condition":
        raise RuntimeError("Terminal reason could not be classified")

    if args.memory_mode == "on":
        case["failure_stage"] = "memory final reopen"
        final_memory = new_memory(env, args, paths["database"])
        final_count = memory_count(final_memory)
        case["memory"]["final_count"] = final_count
        expected = (
            case["memory"]["initial_count"] +
            case["memory"]["successful_write_count"])
        case["memory"]["expected_final_count"] = expected
        append_jsonl(paths["memory_events"], {
            "timestamp_utc": utc_now(), "event": "final_reopen",
            "count": final_count, "expected_count": expected,
        })
        if final_count != expected:
            raise RuntimeError("Final Memory count does not match successful writes")
        del final_memory
        gc.collect()


def initial_case(args, paths):
    scenario_contract = SCENARIOS[args.scenario]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": scenario_contract["protocol_version"],
        "artifact_complete": False,
        "status": "started",
        "failure_stage": "argument and path validation",
        "failure": None,
        "scenario": args.scenario,
        "environment_id": scenario_contract["environment_id"],
        "memory_mode": args.memory_mode,
        "success": None,
        "terminal_reason": None,
        "timestamps": {"started_utc": utc_now(), "completed_utc": None},
        "command": [sys.executable] + sys.argv,
        "paths": {
            key: str(value) if value is not None else None
            for key, value in paths.items()
        },
        "seed": {"requested": args.seed, "effective": None},
        "git": {"commit": None, "dirty": None, "status_short": None},
        "runtime": {},
        "ollama": {
            "endpoint": args.ollama_endpoint,
            "chat_backend": "ollama",
            "requested_chat_model": args.chat_model,
            "timeout_seconds": args.timeout,
            "sampling": "provider defaults; not guaranteed deterministic",
        },
        "environment": {},
        "initial_state_sha256": None,
        "episode": {
            "steps": 0, "simulation_substeps": 0,
            "simulation_time_seconds": 0.0, "total_reward": 0.0,
            "wall_clock_runtime_seconds": None,
        },
        "counters": {
            "llm_calls": 0, "negotiation_calls": 0, "decision_calls": 0,
            "parser_failures": 0, "negotiation_parser_failures": 0,
            "decision_parser_failures": 0, "fallback_actions": 0,
            "declared_action_space_mismatch_steps": 0,
        },
        "memory": {
            "mode": args.memory_mode,
            "contract": (
                "independent-episode Memory ON" if args.memory_mode == "on"
                else "Memory OFF; database never instantiated"),
            "database_path": (
                str(paths["database"]) if paths["database"] is not None else None),
            "embedding_backend": "ollama" if args.memory_mode == "on" else None,
            "requested_embedding_model": (
                args.embedding_model if args.memory_mode == "on" else None),
            "initial_count": None if args.memory_mode == "on" else 0,
            "final_count": None if args.memory_mode == "on" else 0,
            "retrieval_count": 0,
            "retrieved_experiences": 0,
            "update_count": 0,
            "successful_write_count": 0,
            "update_timing": (
                "after each CAV decision and before env.step"
                if args.memory_mode == "on" else None),
        },
    }


def main(argv=None):
    args = parse_args(argv)
    paths = build_paths(args)
    paths["run_directory"].mkdir(parents=True, exist_ok=False)
    case = initial_case(args, paths)
    atomic_write_json(paths["case"], case)
    started = time.perf_counter()
    state = {"env": None}
    failure = None
    try:
        run_case(args, paths, case, state)
    except Exception as error:
        failure = error
    finally:
        env = state["env"]
        if env is not None:
            try:
                env.close()
            except Exception as close_error:
                if failure is None:
                    failure = close_error
                    case["failure_stage"] = "environment close"

    case["episode"]["wall_clock_runtime_seconds"] = time.perf_counter() - started
    case["timestamps"]["completed_utc"] = utc_now()
    case["artifact_complete"] = True
    if failure is not None:
        case["status"] = "failed"
        case["success"] = False
        case["failure"] = {
            "category": classify_failure(case["failure_stage"]),
            "stage": case["failure_stage"],
            "exception_type": type(failure).__name__,
            "exception_message": str(failure),
        }
        atomic_write_json(paths["case"], case)
        raise failure

    case["status"] = "completed"
    case["failure_stage"] = None
    atomic_write_json(paths["case"], case)
    print(json.dumps({
        "status": case["status"], "success": case["success"],
        "terminal_reason": case["terminal_reason"],
        "case_artifact": str(paths["case"]),
        "initial_state_sha256": case["initial_state_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
