import json
import sys
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
ARTIFACT_PATH = Path("notes/artifacts/phase2c/integrated_single_step_retry2.json")


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


def backend_trace(backend):
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


def save_artifact(artifact):
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(json_safe(artifact), indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Local Reproduction / Thesis Mode",
        "phase": "Phase 2C - Integrated Single-Step Test",
        "backend": "ollama",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "memory": {
            "mode": "Memory OFF",
            "database_path": None,
            "initial_database_state": "not instantiated",
            "stored_experiences": None,
            "retrieval_count": 0,
        },
        "episode_count": 0,
        "policy_steps_requested": 1,
        "status": "started",
    }

    env = gym.make("intersection-multi-agent-v0")
    initial_observation = env.reset()
    artifact["environment"] = {
        "id": env.spec.id,
        "configured_seed": env.config.get("seed"),
        "observation_type": type(initial_observation).__name__,
        "observation_shape": getattr(initial_observation, "shape", None),
        "action_space": str(env.action_space),
        "controlled_vehicle_count": len(env.controlled_vehicles),
        "road_vehicle_count": len(env.road.vehicles),
        "background_vehicle_count": len([
            vehicle for vehicle in env.road.vehicles
            if vehicle not in env.controlled_vehicles
        ]),
        "controlled_vehicles_before": [str(vehicle) for vehicle in env.controlled_vehicles],
    }
    save_artifact(artifact)

    negotiation_agent = LlmAgent_negotiation_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)
    negotiation_content, conflicting_info = negotiation_agent.llm_controller_run(env)

    action_agent = LlmAgent_action_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)
    parsed_by_vehicle = {}
    for vehicle in env.controlled_vehicles:
        vehicle_id = str(vehicle).split(":")[0].strip()
        parsed_by_vehicle[vehicle_id] = action_agent.extract_vehicle_conflicts(
            negotiation_content, vehicle_id)

    artifact["negotiation"] = {
        "transport": backend_trace(negotiation_agent.chat_backend),
        "conflicting_vehicle_info": [
            {key: str(value) if key in {"vehicle_i", "vehicle_j"} else value
             for key, value in item.items()}
            for item in conflicting_info
        ],
        "parsed_by_vehicle": parsed_by_vehicle,
    }
    save_artifact(artifact)
    print("negotiation_raw_content={}".format(repr(negotiation_content)))
    print("negotiation_parsed_by_vehicle={}".format(parsed_by_vehicle))

    if conflicting_info and sum(len(items) for items in parsed_by_vehicle.values()) == 0:
        artifact["status"] = "blocked: negotiation parser produced no conflicts"
        save_artifact(artifact)
        raise RuntimeError("Original negotiation parser did not parse the Ollama response")

    decisions = []
    action_ids = []
    for index, ego_vehicle in enumerate(env.controlled_vehicles):
        if action_agent.get_scene_name(env) == "intersection":
            speed_limit = 5
        else:
            speed_limit = 20
        ego_vehicle.speed = speed_limit if ego_vehicle.speed > speed_limit else ego_vehicle.speed

        negotiation_results = action_agent.transfer_negotiation_prompts_to_results(
            ego_vehicle, negotiation_content)
        current_scenario = action_agent.prompt_engineer(
            ego_vehicle, env.road, env, negotiation_results, conflicting_info)
        llm_action = action_agent.send_to_chatgpt(
            ego_vehicle, current_scenario, negotiation_results, memory=None)
        raw_content = action_agent.chat_backend.last_content
        semantic_action = action_agent.extract_decision(raw_content)
        action_id = int(llm_action[0])
        decision = {
            "cav_index": index,
            "ego_vehicle": str(ego_vehicle),
            "negotiation_results": negotiation_results,
            "current_scenario": current_scenario,
            "transport": backend_trace(action_agent.chat_backend),
            "semantic_action": semantic_action,
            "action_id": action_id,
        }
        decisions.append(decision)
        artifact["decisions"] = decisions
        save_artifact(artifact)
        print("cav_{}_raw_content={}".format(index, repr(raw_content)))
        print("cav_{}_semantic_action={}".format(index, semantic_action))
        print("cav_{}_action_id={}".format(index, action_id))

        if semantic_action not in action_agent.ACTIONS_ALL.values():
            artifact["status"] = "blocked: invalid semantic action for CAV {}".format(index)
            save_artifact(artifact)
            raise RuntimeError("Original decision parser returned an invalid semantic action")
        if action_id not in action_agent.ACTIONS_ALL:
            artifact["status"] = "blocked: invalid action ID for CAV {}".format(index)
            save_artifact(artifact)
            raise RuntimeError("Original action mapping returned an invalid action ID")
        action_ids.append(action_id)

    joint_action = tuple(action_ids)
    artifact["joint_action"] = list(joint_action)
    artifact["joint_action_space_contains"] = env.action_space.contains(joint_action)
    executable_action_maps = [
        action_type.actions for action_type in env.action_type.agents_action_types
    ]
    artifact["executable_action_maps"] = executable_action_maps
    artifact["joint_action_executable"] = all(
        action_id in action_map
        for action_id, action_map in zip(joint_action, executable_action_maps)
    )
    save_artifact(artifact)
    print("joint_action={}".format(joint_action))
    print("joint_action_space_contains={}".format(artifact["joint_action_space_contains"]))
    print("joint_action_executable={}".format(artifact["joint_action_executable"]))

    if not artifact["joint_action_executable"]:
        artifact["status"] = "blocked: joint action unsupported by executable action maps"
        save_artifact(artifact)
        raise RuntimeError("Joint action is unsupported by the original executable action maps")

    next_observation, reward, terminal, info = env.step(joint_action, env)
    artifact["step"] = {
        "observation_type": type(next_observation).__name__,
        "observation_shape": getattr(next_observation, "shape", None),
        "reward": reward,
        "terminal": terminal,
        "info": info,
    }
    artifact["status"] = "success: exactly one integrated policy step"
    save_artifact(artifact)

    print("step_reward={}".format(reward))
    print("step_terminal={}".format(terminal))
    print("step_info={}".format(info))
    print("artifact={}".format(ARTIFACT_PATH))
    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
