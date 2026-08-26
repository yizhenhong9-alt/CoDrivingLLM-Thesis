import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import gym
import numpy as np
import highway_env  # noqa: F401 - importing registers repository-local environments

from llm_controller.llm_agent_action import LlmAgent_action_module
from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module


MODEL = "qwen2.5:7b"
ENDPOINT = "http://127.0.0.1:11435"
TIMEOUT = 120
ARTIFACT_PATH = Path("notes/artifacts/phase2d/full_episode_memory_off.json")


def json_safe(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def transport_trace(backend):
    return {
        "backend": backend.backend,
        "endpoint": backend.endpoint,
        "model": backend.model,
        "timeout_seconds": backend.timeout,
        "stream": False,
        "sampling_parameters": "provider defaults",
        "messages": backend.last_messages,
        "raw_response": backend.last_raw_response,
        "raw_content": backend.last_content,
        "latency_seconds": backend.last_latency_seconds,
    }


def write_artifact(artifact):
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(json_safe(artifact), indent=2, ensure_ascii=False), encoding="utf-8")


def vehicle_id(vehicle):
    return str(vehicle).split(":")[0].strip()


def terminal_reason(env):
    if any(vehicle.crashed for vehicle in env.controlled_vehicles):
        return "controlled_vehicle_crash"
    if all(env.has_arrived(vehicle) for vehicle in env.controlled_vehicles):
        return "all_controlled_vehicles_arrived"
    if env.steps >= env.config["duration"] * env.config["policy_frequency"] - 1:
        return "duration_limit"
    if env.config["offroad_terminal"] and not env.vehicle.on_road:
        return "offroad"
    return "unknown_terminal_condition"


def main():
    started = time.perf_counter()
    artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Local Reproduction / Thesis Mode",
        "phase": "First complete Ollama episode test",
        "repository_head": "60cc9a3f4bd9f865aab3964e9b8c6d706b688e0a",
        "backend": "ollama",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "timeout_seconds": TIMEOUT,
        "memory": {
            "mode": "Memory OFF",
            "database_path": None,
            "initial_database_state": "not instantiated",
            "stored_experiences": None,
            "retrieval_count": 0,
            "update_count": 0,
        },
        "episode_requested": 1,
        "status": "started",
        "counters": {
            "completed_policy_steps": 0,
            "negotiation_calls": 0,
            "decision_calls": 0,
            "negotiation_parser_failures": 0,
            "decision_parser_failures": 0,
        },
        "latency_seconds": {
            "negotiation_total": 0.0,
            "decision_total": 0.0,
            "llm_total": 0.0,
        },
        "cumulative_reward": 0.0,
        "steps": [],
    }

    env = gym.make("intersection-multi-agent-v0")
    initial_observation = env.reset()
    artifact["environment"] = {
        "id": env.spec.id,
        "configured_seed": env.config.get("seed"),
        "duration": env.config.get("duration"),
        "policy_frequency": env.config.get("policy_frequency"),
        "maximum_terminal_step": env.config["duration"] * env.config["policy_frequency"] - 1,
        "observation_type": type(initial_observation).__name__,
        "observation_shape": getattr(initial_observation, "shape", None),
        "action_space": str(env.action_space),
        "controlled_vehicle_count": len(env.controlled_vehicles),
        "initial_road_vehicle_count": len(env.road.vehicles),
        "initial_controlled_vehicles": [str(vehicle) for vehicle in env.controlled_vehicles],
    }
    write_artifact(artifact)

    negotiation_agent = LlmAgent_negotiation_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)
    action_agent = LlmAgent_action_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)

    terminal = False
    while not terminal:
        step_index = artifact["counters"]["completed_policy_steps"]
        step_record = {
            "step_index": step_index,
            "environment_steps_before": env.steps,
            "controlled_vehicles_before": [str(vehicle) for vehicle in env.controlled_vehicles],
        }
        artifact["active_step"] = step_record
        write_artifact(artifact)

        negotiation_content, conflicting_info = negotiation_agent.llm_controller_run(env)
        artifact["counters"]["negotiation_calls"] += 1
        negotiation_latency = negotiation_agent.chat_backend.last_latency_seconds
        artifact["latency_seconds"]["negotiation_total"] += negotiation_latency
        artifact["latency_seconds"]["llm_total"] += negotiation_latency

        parsed_by_vehicle = {}
        parsed_pairs = set()
        for vehicle in env.controlled_vehicles:
            identifier = vehicle_id(vehicle)
            parsed = action_agent.extract_vehicle_conflicts(negotiation_content, identifier)
            parsed_by_vehicle[identifier] = parsed
            parsed_pairs.update((first, second) for first, second, _ in parsed)
        expected_pairs = {
            (vehicle_id(item["vehicle_i"]), vehicle_id(item["vehicle_j"]))
            for item in conflicting_info
        }
        expected_pairs |= {(second, first) for first, second in list(expected_pairs)}
        parsed_pairs_bidirectional = parsed_pairs | {
            (second, first) for first, second in parsed_pairs
        }

        step_record["negotiation"] = {
            "transport": transport_trace(negotiation_agent.chat_backend),
            "conflicting_vehicle_info": [
                {key: str(value) if key in {"vehicle_i", "vehicle_j"} else value
                 for key, value in item.items()}
                for item in conflicting_info
            ],
            "parsed_by_vehicle": parsed_by_vehicle,
            "expected_pair_count": len(conflicting_info),
            "parsed_pair_count": len(parsed_pairs),
        }
        write_artifact(artifact)

        if expected_pairs and not expected_pairs.issubset(parsed_pairs_bidirectional):
            artifact["counters"]["negotiation_parser_failures"] += 1
            artifact["status"] = "blocked: negotiation parser failure at step {}".format(step_index)
            artifact["episode_runtime_seconds"] = time.perf_counter() - started
            write_artifact(artifact)
            raise RuntimeError("Negotiation parser did not cover every real conflict pair")

        decisions = []
        action_ids = []
        for cav_index, ego_vehicle in enumerate(env.controlled_vehicles):
            speed_limit = 5 if action_agent.get_scene_name(env) == "intersection" else 20
            ego_vehicle.speed = speed_limit if ego_vehicle.speed > speed_limit else ego_vehicle.speed
            negotiation_results = action_agent.transfer_negotiation_prompts_to_results(
                ego_vehicle, negotiation_content)
            current_scenario = action_agent.prompt_engineer(
                ego_vehicle, env.road, env, negotiation_results, conflicting_info)
            llm_action = action_agent.send_to_chatgpt(
                ego_vehicle, current_scenario, negotiation_results, memory=None)
            artifact["counters"]["decision_calls"] += 1
            decision_latency = action_agent.chat_backend.last_latency_seconds
            artifact["latency_seconds"]["decision_total"] += decision_latency
            artifact["latency_seconds"]["llm_total"] += decision_latency
            semantic_action = action_agent.extract_decision(
                action_agent.chat_backend.last_content)
            action_id = int(llm_action[0])
            decision_record = {
                "cav_index": cav_index,
                "ego_vehicle": str(ego_vehicle),
                "negotiation_results": negotiation_results,
                "current_scenario": current_scenario,
                "transport": transport_trace(action_agent.chat_backend),
                "semantic_action": semantic_action,
                "action_id": action_id,
            }
            decisions.append(decision_record)
            step_record["decisions"] = decisions
            write_artifact(artifact)

            if semantic_action not in action_agent.ACTIONS_ALL.values():
                artifact["counters"]["decision_parser_failures"] += 1
                artifact["status"] = "blocked: decision parser failure at step {}, CAV {}".format(
                    step_index, cav_index)
                artifact["episode_runtime_seconds"] = time.perf_counter() - started
                write_artifact(artifact)
                raise RuntimeError("Decision parser returned an invalid semantic action")
            if action_id not in action_agent.ACTIONS_ALL:
                artifact["counters"]["decision_parser_failures"] += 1
                artifact["status"] = "blocked: invalid action ID at step {}, CAV {}".format(
                    step_index, cav_index)
                artifact["episode_runtime_seconds"] = time.perf_counter() - started
                write_artifact(artifact)
                raise RuntimeError("Decision mapping returned an invalid action ID")
            action_ids.append(action_id)

        joint_action = tuple(action_ids)
        executable_action_maps = [
            action_type.actions for action_type in env.action_type.agents_action_types
        ]
        step_record["joint_action"] = list(joint_action)
        step_record["joint_action_space_contains"] = env.action_space.contains(joint_action)
        step_record["joint_action_executable"] = all(
            action_id in action_map
            for action_id, action_map in zip(joint_action, executable_action_maps)
        )
        step_record["executable_action_maps"] = executable_action_maps
        write_artifact(artifact)
        if not step_record["joint_action_executable"]:
            artifact["status"] = "blocked: non-executable joint action at step {}".format(step_index)
            artifact["episode_runtime_seconds"] = time.perf_counter() - started
            write_artifact(artifact)
            raise RuntimeError("Joint action is unsupported by original executable action maps")

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
            "controlled_vehicles_after": [str(vehicle) for vehicle in env.controlled_vehicles],
            "controlled_crash_status": [bool(vehicle.crashed) for vehicle in env.controlled_vehicles],
            "controlled_arrival_status": [bool(env.has_arrived(vehicle)) for vehicle in env.controlled_vehicles],
        }
        artifact["steps"].append(step_record)
        artifact.pop("active_step", None)
        print(
            "step={} joint_action={} reward={} cumulative_reward={} terminal={}".format(
                step_index, joint_action, reward_value, artifact["cumulative_reward"], terminal),
            flush=True,
        )
        write_artifact(artifact)

    artifact["status"] = "success: one complete episode"
    artifact["terminal_reason"] = terminal_reason(env)
    artifact["final_crash_status"] = [
        bool(vehicle.crashed) for vehicle in env.controlled_vehicles
    ]
    artifact["final_arrival_status"] = [
        bool(env.has_arrived(vehicle)) for vehicle in env.controlled_vehicles
    ]
    artifact["episode_runtime_seconds"] = time.perf_counter() - started
    write_artifact(artifact)
    print("terminal_reason={}".format(artifact["terminal_reason"]), flush=True)
    print("episode_runtime_seconds={}".format(artifact["episode_runtime_seconds"]), flush=True)
    print("artifact={}".format(ARTIFACT_PATH), flush=True)
    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
