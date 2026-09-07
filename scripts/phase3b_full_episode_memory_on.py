import argparse
import gc
import importlib.metadata
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import gym
import highway_env  # noqa: F401 - importing registers repository-local environments

from llm_controller.llm_agent_action import LlmAgent_action_module
from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module
from llm_controller.memory import DrivingMemory
from scripts.phase2d_full_episode import (
    json_safe,
    terminal_reason,
    transport_trace,
    vehicle_id,
)
from scripts.phase3a_memory_on_preflight import (
    KNOWN_DATABASE_ROOTS,
    extract_memory_section,
    git_value,
    is_within,
    memory_count,
    read_json,
    resolve_model,
)


MODE = "Local Reproduction / Thesis Memory Mode adaptation"
ENVIRONMENT_ID = "intersection-multi-agent-v0"
REQUIRED_PACKAGE_VERSIONS = {
    "langchain": "0.0.335",
    "chromadb": "0.4.15",
    "tokenizers": "0.13.3",
    "posthog": "3.8.4",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="First controlled full Phase 3B Memory ON episode")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ollama-endpoint", required=True)
    parser.add_argument("--chat-model", required=True)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("{} must be an absolute path".format(label))
    return path.resolve(strict=False)


def validate_output_paths(output_root, run_dir, database_path, artifact_path):
    if output_root.exists() and not output_root.is_dir():
        raise ValueError("Output root exists but is not a directory")
    if run_dir.exists():
        raise FileExistsError("Phase 3B run directory already exists; refusing reuse")
    if not is_within(run_dir, output_root) or run_dir == output_root:
        raise ValueError("Run directory must be strictly inside output root")
    if not is_within(database_path, run_dir) or database_path == run_dir:
        raise ValueError("Database path must be strictly inside the fresh run directory")
    if is_within(artifact_path, database_path) or artifact_path == database_path:
        raise ValueError("Artifact path must be outside the Chroma database directory")

    for known_root_value in KNOWN_DATABASE_ROOTS:
        known_root = known_root_value.resolve(strict=False)
        if (output_root == known_root or is_within(output_root, known_root) or
                is_within(known_root, output_root)):
            raise ValueError("Output root overlaps a known original/historical database root")
        if database_path == known_root or is_within(database_path, known_root):
            raise ValueError("Database path is inside a known original/historical database root")


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def validate_runtime_versions():
    versions = {
        name: package_version(name) for name in REQUIRED_PACKAGE_VERSIONS
    }
    if sys.version_info[:3] != (3, 8, 20):
        raise RuntimeError("Phase 3B requires Python 3.8.20")
    mismatches = {
        name: {"expected": expected, "actual": versions[name]}
        for name, expected in REQUIRED_PACKAGE_VERSIONS.items()
        if versions[name] != expected
    }
    if mismatches:
        raise RuntimeError("Phase 3B package version mismatch: {}".format(mismatches))
    return versions


def write_artifact(path, artifact):
    path.write_text(
        json.dumps(json_safe(artifact), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def complete_checkpoint(artifact_path, artifact, name):
    artifact["completed_checkpoints"].append(name)
    write_artifact(artifact_path, artifact)


def model_inventory(endpoint, timeout, chat_model, embedding_model):
    base_url = endpoint.rstrip("/")
    version_response = read_json(base_url + "/api/version", timeout)
    tags_response = read_json(base_url + "/api/tags", timeout)
    return {
        "version_response": version_response,
        "chat_model": resolve_model(tags_response, chat_model),
        "embedding_model": resolve_model(tags_response, embedding_model),
    }


def serialize_conflicting_info(conflicting_info):
    return [
        {
            key: str(value) if key in {"vehicle_i", "vehicle_j"} else value
            for key, value in item.items()
        }
        for item in conflicting_info
    ]


def new_memory(env, args, database_path):
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


def run_episode(args, database_path, artifact_path, artifact, runtime_state):
    artifact["failure_stage"] = "runtime and repository identity"
    repository_head = git_value("rev-parse", "HEAD")
    if repository_head is None:
        raise RuntimeError("Git commit identity could not be resolved")
    artifact["repository"] = {
        "head": repository_head,
        "status_short": git_value("status", "--short"),
        "working_directory": os.getcwd(),
    }
    artifact["runtime"] = {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "os": platform.platform(),
        "conda_prefix": os.environ.get("CONDA_PREFIX"),
        "highway_env_import_path": highway_env.__file__,
        "package_versions": validate_runtime_versions(),
    }
    complete_checkpoint(
        artifact_path, artifact, "validated repository and runtime versions")

    artifact["failure_stage"] = "Ollama model inventory"
    inventory = model_inventory(
        args.ollama_endpoint, args.timeout, args.chat_model, args.embedding_model)
    artifact["ollama"]["version_response"] = inventory["version_response"]
    artifact["chat"]["resolved_model"] = inventory["chat_model"]
    artifact["embedding"]["resolved_model"] = inventory["embedding_model"]
    complete_checkpoint(
        artifact_path, artifact, "resolved Ollama chat and embedding model digests")

    artifact["failure_stage"] = "environment and fresh memory initialization"
    env = gym.make(ENVIRONMENT_ID)
    runtime_state["env"] = env
    initial_observation = env.reset()
    artifact["environment"] = {
        "id": env.spec.id,
        "configured_seed": env.config.get("seed"),
        "duration": env.config.get("duration"),
        "policy_frequency": env.config.get("policy_frequency"),
        "maximum_terminal_step": (
            env.config["duration"] * env.config["policy_frequency"] - 1),
        "observation_type": type(initial_observation).__name__,
        "observation_shape": getattr(initial_observation, "shape", None),
        "action_space": str(env.action_space),
        "controlled_vehicle_count": len(env.controlled_vehicles),
        "initial_road_vehicle_count": len(env.road.vehicles),
        "initial_controlled_vehicles": [
            str(vehicle) for vehicle in env.controlled_vehicles
        ],
    }

    initial_memory = new_memory(env, args, database_path)
    initial_count = memory_count(initial_memory)
    artifact["memory"]["initial_count"] = initial_count
    if initial_count != 0:
        raise RuntimeError("Fresh Phase 3B memory database is not empty")
    del initial_memory
    gc.collect()
    complete_checkpoint(
        artifact_path, artifact, "created and verified fresh empty memory database")

    negotiation_agent = LlmAgent_negotiation_module(
        env,
        backend="ollama",
        model=args.chat_model,
        endpoint=args.ollama_endpoint,
        timeout=args.timeout,
    )
    action_agent = LlmAgent_action_module(
        env,
        backend="ollama",
        model=args.chat_model,
        endpoint=args.ollama_endpoint,
        timeout=args.timeout,
        memory_mode="on",
    )

    terminal = False
    while not terminal:
        step_index = artifact["counters"]["completed_policy_steps"]
        artifact["failure_stage"] = "policy step {}".format(step_index)
        memory = new_memory(env, args, database_path)
        step_record = {
            "step_index": step_index,
            "environment_steps_before": env.steps,
            "memory_count_before": memory_count(memory),
            "controlled_vehicles_before": [
                str(vehicle) for vehicle in env.controlled_vehicles
            ],
        }
        artifact["active_step"] = step_record
        write_artifact(artifact_path, artifact)

        negotiation_content, conflicting_info = negotiation_agent.llm_controller_run(env)
        artifact["counters"]["negotiation_calls"] += 1
        negotiation_latency = negotiation_agent.chat_backend.last_latency_seconds
        artifact["latency_seconds"]["negotiation_total"] += negotiation_latency
        artifact["latency_seconds"]["llm_total"] += negotiation_latency

        parsed_by_vehicle = {}
        parsed_pairs = set()
        for vehicle in env.controlled_vehicles:
            identifier = vehicle_id(vehicle)
            parsed = action_agent.extract_vehicle_conflicts(
                negotiation_content, identifier)
            parsed_by_vehicle[identifier] = parsed
            parsed_pairs.update((first, second) for first, second, _ in parsed)
        expected_pairs = {
            (vehicle_id(item["vehicle_i"]), vehicle_id(item["vehicle_j"]))
            for item in conflicting_info
        }
        expected_pairs |= {
            (second, first) for first, second in list(expected_pairs)
        }
        parsed_pairs_bidirectional = parsed_pairs | {
            (second, first) for first, second in parsed_pairs
        }
        step_record["negotiation"] = {
            "transport": transport_trace(negotiation_agent.chat_backend),
            "conflicting_vehicle_info": serialize_conflicting_info(conflicting_info),
            "parsed_by_vehicle": parsed_by_vehicle,
            "expected_pair_count": len(conflicting_info),
            "parsed_pair_count": len(parsed_pairs),
        }
        write_artifact(artifact_path, artifact)

        if expected_pairs and not expected_pairs.issubset(parsed_pairs_bidirectional):
            artifact["counters"]["negotiation_parser_failures"] += 1
            raise RuntimeError(
                "Negotiation parser did not cover every real conflict pair")

        decisions = []
        action_ids = []
        for cav_index, ego_vehicle in enumerate(env.controlled_vehicles):
            speed_limit = (
                5 if action_agent.get_scene_name(env) == "intersection" else 20)
            ego_vehicle.speed = (
                speed_limit if ego_vehicle.speed > speed_limit else ego_vehicle.speed)
            negotiation_results = (
                action_agent.transfer_negotiation_prompts_to_results(
                    ego_vehicle, negotiation_content))
            current_scenario = action_agent.prompt_engineer(
                ego_vehicle, env.road, env, negotiation_results, conflicting_info)

            llm_action = action_agent.send_to_chatgpt(
                ego_vehicle, current_scenario, negotiation_results, memory)
            artifact["counters"]["decision_calls"] += 1
            artifact["memory"]["retrieval_calls"] += 1
            decision_latency = action_agent.chat_backend.last_latency_seconds
            artifact["latency_seconds"]["decision_total"] += decision_latency
            artifact["latency_seconds"]["llm_total"] += decision_latency
            retrieval_latency = memory.embedding.last_latency_seconds
            artifact["latency_seconds"]["embedding_total"] += retrieval_latency

            semantic_action = action_agent.extract_decision(
                action_agent.chat_backend.last_content)
            action_id = int(llm_action[0])
            retrieved_metadata = memory.last_retrieval_results
            retrieved_count = len(retrieved_metadata)
            artifact["memory"]["retrieved_experiences_total"] += retrieved_count
            formatted_memory = action_agent.format_relative_memory(
                retrieved_metadata)
            final_prompt = action_agent.chat_backend.last_messages[0]["content"]
            extracted_memory = extract_memory_section(final_prompt)
            memory_inserted = extracted_memory == formatted_memory
            expected_query = "\n".join(
                current_scenario.strip().split("\n")[-2:])
            query_matches_original = (
                memory.last_retrieval_query == expected_query)

            decision_record = {
                "cav_index": cav_index,
                "ego_vehicle": str(ego_vehicle),
                "negotiation_results": negotiation_results,
                "current_scenario": current_scenario,
                "transport": transport_trace(action_agent.chat_backend),
                "semantic_action": semantic_action,
                "action_id": action_id,
                "memory": {
                    "query": memory.last_retrieval_query,
                    "expected_original_query": expected_query,
                    "query_matches_original_construction": (
                        query_matches_original),
                    "top_k": memory.last_retrieval_top_k,
                    "retrieved_count": retrieved_count,
                    "retrieved_metadata": retrieved_metadata,
                    "retrieval_scores": memory.last_retrieval_scores,
                    "formatted_memory": formatted_memory,
                    "extracted_prompt_memory": extracted_memory,
                    "inserted_exactly": memory_inserted,
                },
            }
            decisions.append(decision_record)
            step_record["decisions"] = decisions
            write_artifact(artifact_path, artifact)

            if semantic_action not in action_agent.ACTIONS_ALL.values():
                artifact["counters"]["decision_parser_failures"] += 1
                raise RuntimeError(
                    "Decision parser returned an invalid semantic action")
            if action_id not in action_agent.ACTIONS_ALL:
                artifact["counters"]["decision_parser_failures"] += 1
                raise RuntimeError("Decision mapping returned an invalid action ID")
            if (not query_matches_original
                    or memory.last_retrieval_top_k != 2
                    or not memory_inserted):
                raise RuntimeError(
                    "Memory retrieval or exact prompt insertion validation failed")

            count_before_update = memory_count(memory)
            artifact["memory"]["update_calls"] += 1
            action_agent.memory_update(memory, current_scenario, llm_action)
            update_latency = memory.embedding.last_latency_seconds
            artifact["latency_seconds"]["embedding_total"] += update_latency
            count_after_update = memory_count(memory)
            update_success = count_after_update == count_before_update + 1
            decision_record["memory"]["update"] = {
                "page_content": memory.last_added_page_content,
                "metadata": memory.last_added_metadata,
                "count_before": count_before_update,
                "count_after": count_after_update,
                "successful_write": update_success,
                "timing": "after decision and before env.step",
            }
            if not update_success:
                raise RuntimeError("Memory update did not increase item count by one")
            artifact["memory"]["successful_writes"] += 1
            action_ids.append(action_id)
            write_artifact(artifact_path, artifact)

        step_record["memory_count_after_updates"] = memory_count(memory)
        step_record["embedding_request_count"] = memory.embedding.request_count
        artifact["counters"]["embedding_calls"] += memory.embedding.request_count
        if memory.embedding.vector_dimension is not None:
            artifact["embedding"]["vector_dimension"] = (
                memory.embedding.vector_dimension)

        joint_action = tuple(action_ids)
        executable_action_maps = [
            action_type.actions for action_type in env.action_type.agents_action_types
        ]
        step_record["joint_action"] = list(joint_action)
        step_record["joint_action_space_contains"] = (
            env.action_space.contains(joint_action))
        step_record["joint_action_executable"] = all(
            action_id in action_map
            for action_id, action_map in zip(joint_action, executable_action_maps)
        )
        step_record["executable_action_maps"] = executable_action_maps
        if not step_record["joint_action_executable"]:
            raise RuntimeError(
                "Joint action is unsupported by original executable action maps")

        next_observation, reward, terminal, info = env.step(joint_action, env)
        reward_value = float(reward)
        artifact["cumulative_reward"] += reward_value
        artifact["counters"]["completed_policy_steps"] += 1
        step_record["transition"] = {
            "environment_steps_after": env.steps,
            "observation_type": type(next_observation).__name__,
            "observation_shape": getattr(next_observation, "shape", None),
            "reward": reward_value,
            "terminal": bool(terminal),
            "info": info,
            "controlled_vehicles_after": [
                str(vehicle) for vehicle in env.controlled_vehicles
            ],
            "controlled_crash_status": [
                bool(vehicle.crashed) for vehicle in env.controlled_vehicles
            ],
            "controlled_arrival_status": [
                bool(env.has_arrived(vehicle)) for vehicle in env.controlled_vehicles
            ],
        }
        artifact["steps"].append(step_record)
        artifact.pop("active_step", None)
        write_artifact(artifact_path, artifact)
        print(
            "step={} joint_action={} reward={} cumulative_reward={} terminal={} "
            "memory_count={}".format(
                step_index,
                joint_action,
                reward_value,
                artifact["cumulative_reward"],
                terminal,
                step_record["memory_count_after_updates"],
            ),
            flush=True,
        )
        del memory
        gc.collect()

    artifact["failure_stage"] = "final memory reopen and episode summary"
    final_memory = new_memory(env, args, database_path)
    final_count = memory_count(final_memory)
    artifact["memory"]["final_count"] = final_count
    artifact["memory"]["final_reopen_succeeded"] = True
    expected_final_count = (
        artifact["memory"]["initial_count"] +
        artifact["memory"]["successful_writes"])
    artifact["memory"]["expected_final_count"] = expected_final_count
    if final_count != expected_final_count:
        raise RuntimeError("Final memory count does not match successful writes")

    artifact["terminal_reason"] = terminal_reason(env)
    artifact["final_crash_status"] = [
        bool(vehicle.crashed) for vehicle in env.controlled_vehicles
    ]
    artifact["final_arrival_status"] = [
        bool(env.has_arrived(vehicle)) for vehicle in env.controlled_vehicles
    ]
    del final_memory
    gc.collect()
    complete_checkpoint(
        artifact_path, artifact, "completed one episode and verified final memory")


def main():
    args = parse_args()
    output_root = absolute_path(args.output_root, "output root")
    if not args.run_id or any(character in args.run_id for character in "\\/:"):
        raise ValueError("run-id must be a non-empty directory-safe name")
    run_dir = output_root / args.run_id
    database_path = run_dir / "chroma"
    artifact_path = run_dir / "full_episode_memory_on.json"
    validate_output_paths(
        output_root, run_dir, database_path, artifact_path)
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    started = time.perf_counter()
    artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 3B - First Controlled Full Memory ON Episode",
        "mode": MODE,
        "status": "started",
        "failure_stage": "initialization",
        "completed_checkpoints": [],
        "command": [sys.executable] + sys.argv,
        "episode_requested": 1,
        "output": {
            "run_directory": str(run_dir),
            "artifact_path": str(artifact_path),
        },
        "memory": {
            "mode": "Memory ON",
            "embedding_backend": "ollama",
            "database_path": str(database_path),
            "initial_database_state": "fresh isolated target",
            "phase3a_database_reused": False,
            "retrieval_top_k": 2,
            "retrieval_calls": 0,
            "retrieved_experiences_total": 0,
            "update_calls": 0,
            "successful_writes": 0,
            "update_timing": "after each CAV decision and before env.step",
        },
        "ollama": {
            "endpoint": args.ollama_endpoint,
        },
        "chat": {
            "backend": "ollama",
            "requested_model": args.chat_model,
            "timeout_seconds": args.timeout,
            "stream": False,
            "sampling_parameters": "provider defaults",
        },
        "embedding": {
            "backend": "ollama",
            "requested_model": args.embedding_model,
            "request_endpoint": "/api/embed",
            "timeout_seconds": args.timeout,
            "truncate": "not supplied; provider default",
            "dimensions": "not supplied; model default",
            "options": "not supplied; provider default",
        },
        "counters": {
            "completed_policy_steps": 0,
            "negotiation_calls": 0,
            "decision_calls": 0,
            "embedding_calls": 0,
            "negotiation_parser_failures": 0,
            "decision_parser_failures": 0,
            "fallback_actions": 0,
        },
        "latency_seconds": {
            "negotiation_total": 0.0,
            "decision_total": 0.0,
            "llm_total": 0.0,
            "embedding_total": 0.0,
        },
        "cumulative_reward": 0.0,
        "steps": [],
    }
    write_artifact(artifact_path, artifact)

    runtime_state = {"env": None}
    failure = None
    try:
        run_episode(args, database_path, artifact_path, artifact, runtime_state)
    except Exception as exception:
        failure = exception
    finally:
        env = runtime_state["env"]
        if env is not None:
            try:
                env.close()
            except Exception as close_exception:
                if failure is None:
                    failure = close_exception
                    artifact["failure_stage"] = "environment close"

    artifact["episode_runtime_seconds"] = time.perf_counter() - started
    if failure is not None:
        artifact["status"] = "failed"
        artifact["exception_type"] = type(failure).__name__
        artifact["exception_message"] = str(failure)
        write_artifact(artifact_path, artifact)
        raise failure

    artifact["status"] = "success"
    artifact["timestamp_completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_artifact(artifact_path, artifact)
    print("terminal_reason={}".format(artifact["terminal_reason"]), flush=True)
    print("episode_runtime_seconds={}".format(
        artifact["episode_runtime_seconds"]), flush=True)
    print("artifact={}".format(artifact_path), flush=True)
    print("memory_database={}".format(database_path), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
