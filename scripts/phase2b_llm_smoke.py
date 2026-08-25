import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import gym
import highway_env  # noqa: F401 - importing registers repository-local environments

from llm_controller.llm_agent_action import LlmAgent_action_module
from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module


MODEL = "qwen2.5:7b"
ENDPOINT = "http://127.0.0.1:11435"
TIMEOUT = 120
ARTIFACT_DIR = Path("notes/artifacts/phase2b")


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


def save_artifact(name, artifact):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main():
    env = gym.make("intersection-multi-agent-v0")
    env.reset()

    negotiation = LlmAgent_negotiation_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)
    detected_conflicts = negotiation.detect_conflicts(env)
    negotiation_content, conflicting_info = negotiation.send_to_chatgpt(env, detected_conflicts)

    action_agent = LlmAgent_action_module(
        env, backend="ollama", model=MODEL, endpoint=ENDPOINT, timeout=TIMEOUT)
    parsed_by_vehicle = {}
    for vehicle in env.controlled_vehicles:
        vehicle_id = str(vehicle).split(":")[0].strip()
        parsed_by_vehicle[vehicle_id] = action_agent.extract_vehicle_conflicts(
            negotiation_content, vehicle_id)

    negotiation_artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Local Reproduction / Thesis Mode",
        "environment_id": env.spec.id,
        "memory": "out of scope",
        "conflicting_vehicle_info": [
            {key: str(value) if "vehicle_" in key and key in {"vehicle_i", "vehicle_j"} else value
             for key, value in item.items()}
            for item in conflicting_info
        ],
        "transport": backend_trace(negotiation.chat_backend),
        "parsed_by_vehicle": parsed_by_vehicle,
    }
    negotiation_path = save_artifact("centralized_negotiation.json", negotiation_artifact)
    parsed_conflict_count = sum(len(items) for items in parsed_by_vehicle.values())
    print("negotiation_artifact={}".format(negotiation_path))
    print("negotiation_raw_content={}".format(repr(negotiation_content)))
    print("negotiation_parsed_by_vehicle={}".format(parsed_by_vehicle))

    if not conflicting_info:
        raise RuntimeError("Negotiation smoke input contains no detected conflicts")
    if parsed_conflict_count == 0:
        raise RuntimeError("Original negotiation parser did not parse any Ollama decision")

    ego_vehicle = env.controlled_vehicles[0]
    negotiation_results = action_agent.transfer_negotiation_prompts_to_results(
        ego_vehicle, negotiation_content)
    current_scenario = action_agent.prompt_engineer(
        ego_vehicle, env.road, env, negotiation_results, conflicting_info)
    llm_action = action_agent.send_to_chatgpt(
        ego_vehicle, current_scenario, negotiation_results, memory=None)
    semantic_action = action_agent.extract_decision(action_agent.chat_backend.last_content)
    action_id = int(llm_action[0])
    decision_artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Local Reproduction / Thesis Mode",
        "environment_id": env.spec.id,
        "ego_vehicle": str(ego_vehicle),
        "negotiation_results": negotiation_results,
        "current_scenario": current_scenario,
        "transport": backend_trace(action_agent.chat_backend),
        "parsed_semantic_action": semantic_action,
        "mapped_action_id": action_id,
        "valid_action_ids": sorted(action_agent.ACTIONS_ALL.keys()),
    }
    decision_path = save_artifact("per_cav_decision.json", decision_artifact)
    print("decision_artifact={}".format(decision_path))
    print("decision_raw_content={}".format(repr(action_agent.chat_backend.last_content)))
    print("decision_semantic_action={}".format(semantic_action))
    print("decision_action_id={}".format(action_id))

    if semantic_action not in action_agent.ACTIONS_ALL.values() or action_id not in action_agent.ACTIONS_ALL:
        raise RuntimeError("Original decision parser/action mapping did not produce a valid action")

    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
