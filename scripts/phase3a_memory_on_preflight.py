import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

import gym
import highway_env  # noqa: F401 - importing registers repository-local environments

from llm_controller.llm_agent_action import LlmAgent_action_module
from llm_controller.embedding_backend import OllamaEmbeddingsAdapter
from llm_controller.memory import DrivingMemory


MODE = "Local Reproduction / Thesis Memory Mode adaptation"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
KNOWN_DATABASE_ROOTS = (
    REPOSITORY_ROOT / "db",
    REPOSITORY_ROOT / "llm_controller" / "chroma",
)
MEMORY_SECTION_PREFIX = (
    "Here is your action when scenarios are similar to the current scenario in the past, "
    "you should learn from past memory try not to take the cation that cause more danger:\n"
)
MEMORY_SECTION_SUFFIX = (
    "\n\nBased on the planning trajectory, you have the following conflicts with other vehicles."
)
RUN_CONTEXT = {
    "artifact": None,
    "artifact_path": None,
    "completed_checkpoints": [],
    "failure_stage": "argument validation",
    "env": None,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Controlled Phase 3A Memory ON preflight")
    parser.add_argument("--database-path", required=True)
    parser.add_argument("--artifact-path", required=True)
    parser.add_argument("--preflight-root", required=True)
    parser.add_argument("--embedding-backend", required=True, choices=["ollama"])
    parser.add_argument("--embedding-endpoint", required=True)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--chat-endpoint", required=True)
    parser.add_argument("--chat-model", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("{} must be an absolute path".format(label))
    return path.resolve(strict=False)


def require_new_absolute_path(value, label):
    path = absolute_path(value, label)
    if path.exists():
        raise FileExistsError("{} already exists; preflight refuses reuse".format(label))
    return path


def is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_preflight_paths(preflight_root, database_path, artifact_path):
    if not preflight_root.exists() or not preflight_root.is_dir():
        raise ValueError("Preflight root must be an existing directory")
    if database_path == preflight_root or not is_within(database_path, preflight_root):
        raise ValueError("Database path must be strictly inside the preflight root")

    known_roots = [root.resolve(strict=False) for root in KNOWN_DATABASE_ROOTS]
    for known_root in known_roots:
        if (preflight_root == known_root or is_within(preflight_root, known_root) or
                known_root == preflight_root or is_within(known_root, preflight_root)):
            raise ValueError("Preflight root overlaps a known original/historical database root")
        if database_path == known_root or is_within(database_path, known_root):
            raise ValueError("Database path is inside a known original/historical database root")
        if artifact_path == known_root or is_within(artifact_path, known_root):
            raise ValueError("Artifact path is inside a known original/historical database root")

    if database_path == artifact_path or is_within(artifact_path, database_path):
        raise ValueError("Artifact path must be outside the Chroma database directory")


def validate_artifact_path(database_path, artifact_path):
    for known_root_value in KNOWN_DATABASE_ROOTS:
        known_root = known_root_value.resolve(strict=False)
        if artifact_path == known_root or is_within(artifact_path, known_root):
            raise ValueError("Artifact path is inside a known original/historical database root")
    if database_path == artifact_path or is_within(artifact_path, database_path):
        raise ValueError("Artifact path must be outside the Chroma database directory")


def extract_memory_section(prompt):
    start = prompt.find(MEMORY_SECTION_PREFIX)
    if start < 0:
        raise ValueError("Decision prompt is missing the Memory section prefix")
    start += len(MEMORY_SECTION_PREFIX)
    end = prompt.find(MEMORY_SECTION_SUFFIX, start)
    if end < 0:
        raise ValueError("Decision prompt is missing the Memory section suffix")
    return prompt[start:end]


def set_stage(stage):
    RUN_CONTEXT["failure_stage"] = stage


def complete_checkpoint(name):
    RUN_CONTEXT["completed_checkpoints"].append(name)
    artifact = RUN_CONTEXT["artifact"]
    artifact["completed_checkpoints"] = list(RUN_CONTEXT["completed_checkpoints"])
    save_artifact(RUN_CONTEXT["artifact_path"], artifact)


def read_json(url, timeout):
    with request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_model(tags_response, requested_model):
    models = tags_response.get("models") if isinstance(tags_response, dict) else None
    if not isinstance(models, list):
        raise ValueError("Ollama tags response is missing models")
    matches = [item for item in models if isinstance(item, dict) and
               requested_model in {item.get("name"), item.get("model")}]
    if len(matches) != 1:
        raise ValueError("Requested embedding model did not resolve uniquely")
    digest = matches[0].get("digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError("Resolved embedding model is missing a digest")
    return matches[0]


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def memory_count(memory):
    return len(memory.scenario_memory._collection.get(
        include=["embeddings"])["embeddings"])


def save_artifact(path, artifact):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_value(*arguments):
    completed = subprocess.run(
        ["git", "-c", "safe.directory={}".format(REPOSITORY_ROOT)] + list(arguments),
        capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def run_preflight():
    args = parse_args()
    preflight_root = absolute_path(args.preflight_root, "preflight root")
    database_path = require_new_absolute_path(args.database_path, "database path")
    artifact_path = require_new_absolute_path(args.artifact_path, "artifact path")
    validate_artifact_path(database_path, artifact_path)
    RUN_CONTEXT["artifact_path"] = artifact_path

    artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 3A - Local Memory ON Preflight",
        "mode": MODE,
        "status": "started",
        "failure_stage": None,
        "completed_checkpoints": [],
        "command": [sys.executable] + sys.argv,
        "working_directory": os.getcwd(),
        "git": {
            "commit": git_value("rev-parse", "HEAD"),
            "status_short": git_value("status", "--short"),
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "os": platform.platform(),
            "conda_prefix": os.environ.get("CONDA_PREFIX"),
            "package_versions": {
                "gym": package_version("gym"),
                "numpy": package_version("numpy"),
                "pandas": package_version("pandas"),
                "langchain": package_version("langchain"),
                "chromadb": package_version("chromadb"),
                "openai": package_version("openai"),
                "tiktoken": package_version("tiktoken"),
            },
            "highway_env_import_path": highway_env.__file__,
        },
        "memory": {
            "mode": "Memory ON",
            "preflight_root": str(preflight_root),
            "database_path": str(database_path),
            "database_existed_before": False,
            "historical_database_used": False,
            "top_k": 2,
            "update_timing": "after per-CAV decision and before env.step",
        },
        "embedding": {
            "backend": args.embedding_backend,
            "endpoint": args.embedding_endpoint,
            "requested_model": args.embedding_model,
            "request_endpoint": "/api/embed",
            "truncate": "not supplied; provider default",
            "dimensions": "not supplied; model default",
            "options": "not supplied; provider default",
            "timeout_seconds": args.timeout,
        },
        "chat": {
            "backend": "ollama",
            "endpoint": args.chat_endpoint,
            "requested_model": args.chat_model,
            "timeout_seconds": args.timeout,
            "stream": False,
            "sampling_parameters": "provider defaults",
        },
        "simulator_steps": 0,
        "episodes": 0,
        "fallback_used": False,
    }
    RUN_CONTEXT["artifact"] = artifact
    save_artifact(artifact_path, artifact)
    set_stage("preflight path isolation")
    validate_preflight_paths(preflight_root, database_path, artifact_path)
    complete_checkpoint("validated isolated preflight paths")

    set_stage("git identity")
    if artifact["git"]["commit"] is None:
        raise RuntimeError("Git commit identity could not be resolved")
    complete_checkpoint("validated git identity")

    set_stage("Ollama inventory and model resolution")
    ollama_endpoint = args.embedding_endpoint.rstrip("/")
    version_response = read_json(ollama_endpoint + "/api/version", args.timeout)
    tags_response = read_json(ollama_endpoint + "/api/tags", args.timeout)
    resolved_model = resolve_model(tags_response, args.embedding_model)
    if args.chat_endpoint.rstrip("/") == ollama_endpoint:
        chat_version_response = version_response
        chat_tags_response = tags_response
    else:
        chat_endpoint = args.chat_endpoint.rstrip("/")
        chat_version_response = read_json(chat_endpoint + "/api/version", args.timeout)
        chat_tags_response = read_json(chat_endpoint + "/api/tags", args.timeout)
    resolved_chat_model = resolve_model(chat_tags_response, args.chat_model)
    artifact["embedding"]["ollama_version_response"] = version_response
    artifact["embedding"]["resolved_model"] = resolved_model
    artifact["chat"]["ollama_version_response"] = chat_version_response
    artifact["chat"]["resolved_model"] = resolved_chat_model
    complete_checkpoint("resolved Ollama version and model digests")

    embedding_config = {
        "endpoint": args.embedding_endpoint,
        "model": args.embedding_model,
        "timeout": args.timeout,
    }

    set_stage("embedding capability probe")
    probe_adapter = OllamaEmbeddingsAdapter(**embedding_config)
    probe_vector = probe_adapter.embed_query(
        "CoDrivingLLM memory preflight embedding probe")
    response_model = probe_adapter.last_raw_response.get("model")
    resolved_names = {args.embedding_model, resolved_model.get("name"),
                      resolved_model.get("model")}
    if response_model is not None and response_model not in resolved_names:
        raise RuntimeError("Embedding response model does not match resolved model identity")
    artifact["embedding"]["probe"] = {
        "vector_dimension": len(probe_vector),
        "response_model": response_model,
        "response_metadata": {
            key: value for key, value in probe_adapter.last_raw_response.items()
            if key != "embeddings"
        },
        "latency_seconds": probe_adapter.last_latency_seconds,
    }
    complete_checkpoint("validated embedding capability without storing vectors")

    set_stage("environment initialization")
    env = gym.make("intersection-multi-agent-v0")
    RUN_CONTEXT["env"] = env
    env.reset()
    artifact["environment"] = {
        "id": env.spec.id,
        "configured_seed": env.config.get("seed"),
        "controlled_vehicle_count": len(env.controlled_vehicles),
    }

    memory = DrivingMemory(
        env,
        embedding_backend=args.embedding_backend,
        embedding_config=embedding_config,
        persist_directory=str(database_path),
    )

    initial_count = memory_count(memory)
    artifact["memory"]["initial_item_count"] = initial_count
    if initial_count != 0:
        raise RuntimeError("Preflight database is not empty")
    complete_checkpoint("created isolated empty database")

    set_stage("first retrieval, prompt injection, and decision")
    action_agent = LlmAgent_action_module(
        env,
        backend="ollama",
        model=args.chat_model,
        endpoint=args.chat_endpoint,
        timeout=args.timeout,
        memory_mode="on",
    )
    ego_vehicle = env.controlled_vehicles[0]
    negotiation_results = ""
    conflicting_info = []
    current_scenario = action_agent.prompt_engineer(
        ego_vehicle, env.road, env, negotiation_results, conflicting_info)
    query_scenario = "\n".join(current_scenario.strip().split("\n")[-2:])
    llm_action = action_agent.send_to_chatgpt(
        ego_vehicle, current_scenario, negotiation_results, memory)
    first_retrieval = memory.last_retrieval_results
    first_past_memory = action_agent.format_relative_memory(first_retrieval)
    final_prompt = action_agent.chat_backend.last_messages[0]["content"]
    extracted_memory_section = extract_memory_section(final_prompt)
    query_matches = memory.last_retrieval_query == query_scenario
    artifact["first_retrieval"] = {
        "query_exact_text": memory.last_retrieval_query,
        "query_sha256": sha256_text(memory.last_retrieval_query),
        "query_matches_original_construction": query_matches,
        "top_k": memory.last_retrieval_top_k,
        "returned_count": len(first_retrieval),
        "returned_metadata": first_retrieval,
        "scores": memory.last_retrieval_scores,
        "formatted_past_memory": first_past_memory,
        "formatted_past_memory_sha256": sha256_text(first_past_memory),
    }
    if first_retrieval:
        raise RuntimeError("First retrieval from empty database returned an experience")
    artifact["decision"] = {
        "ego_vehicle": str(ego_vehicle),
        "current_scenario": current_scenario,
        "negotiation_results": negotiation_results,
        "messages": action_agent.chat_backend.last_messages,
        "raw_response": action_agent.chat_backend.last_raw_response,
        "raw_content": action_agent.chat_backend.last_content,
        "latency_seconds": action_agent.chat_backend.last_latency_seconds,
        "action_id": int(llm_action[0]),
        "final_prompt_sha256": sha256_text(final_prompt),
        "memory_section_present": MEMORY_SECTION_PREFIX in final_prompt,
        "memory_section_exact_match": extracted_memory_section == first_past_memory,
        "extracted_memory_section": extracted_memory_section,
    }
    semantic_action = action_agent.extract_decision(action_agent.chat_backend.last_content)
    artifact["decision"]["semantic_action"] = semantic_action
    if not query_matches or memory.last_retrieval_top_k != 2:
        raise RuntimeError("First retrieval did not preserve original query/top_k semantics")
    if extracted_memory_section != first_past_memory:
        raise RuntimeError("Retrieved memory text was not exactly injected into the decision prompt")
    if semantic_action not in action_agent.ACTIONS_ALL.values():
        raise RuntimeError("Decision parser returned an invalid semantic action")
    if int(llm_action[0]) not in action_agent.ACTIONS_ALL:
        raise RuntimeError("Decision action ID is not executable in original ACTIONS_ALL")
    complete_checkpoint("validated first retrieval, exact prompt injection, and decision")

    set_stage("single original memory update")
    saved_info = current_scenario.strip().split("\n")[-1]
    count_before_update = memory_count(memory)
    action_agent.memory_update(memory, current_scenario, llm_action)
    expected_page_content = memory.last_added_page_content
    expected_metadata = dict(memory.last_added_metadata)
    count_after_update = memory_count(memory)
    artifact["memory_update"] = {
        "saved_info": saved_info,
        "human_question": str(None),
        "negotiation_result": str(None),
        "final_action": str(llm_action),
        "count_before": count_before_update,
        "count_after": count_after_update,
        "timing": "after decision and before env.step",
        "expected_page_content": expected_page_content,
        "expected_metadata": expected_metadata,
    }
    if count_before_update != 0 or count_after_update != 1:
        raise RuntimeError("Memory item count did not change from 0 to 1")
    first_adapter_request_count = memory.embedding.request_count
    complete_checkpoint("verified one memory update and item count 0 to 1")

    set_stage("database reopen and second retrieval")
    del memory
    gc.collect()
    reopened_memory = DrivingMemory(
        env,
        embedding_backend=args.embedding_backend,
        embedding_config=embedding_config,
        persist_directory=str(database_path),
    )
    reopened_count = memory_count(reopened_memory)
    second_past_memory = action_agent.relative_memory(reopened_memory, current_scenario)
    second_retrieval = reopened_memory.last_retrieval_results
    second_query_matches = reopened_memory.last_retrieval_query == query_scenario
    artifact["persistence"] = {
        "reopened_item_count": reopened_count,
        "same_process_reopen": True,
        "cross_process_persistence_tested": False,
    }
    artifact["second_retrieval"] = {
        "query_exact_text": query_scenario,
        "query_sha256": sha256_text(query_scenario),
        "query_matches_original_construction": second_query_matches,
        "top_k": reopened_memory.last_retrieval_top_k,
        "returned_count": len(second_retrieval),
        "returned_metadata": second_retrieval,
        "scores": reopened_memory.last_retrieval_scores,
        "formatted_past_memory": second_past_memory,
        "formatted_past_memory_sha256": sha256_text(second_past_memory),
    }
    if reopened_memory.last_retrieval_top_k != 2 or not second_query_matches:
        raise RuntimeError("Second retrieval did not preserve original query/top_k semantics")
    if reopened_count != 1 or len(second_retrieval) != 1:
        raise RuntimeError("Reopen or second retrieval did not recover one experience")
    if second_retrieval[0] != expected_metadata:
        raise RuntimeError("Reopened retrieval metadata does not match the stored payload")

    artifact["memory_update"]["stored_metadata_after_reopen"] = second_retrieval[0]
    artifact["embedding"]["request_count"] = {
        "capability_probe": probe_adapter.request_count,
        "first_memory_instance": first_adapter_request_count,
        "reopened_memory_instance": reopened_memory.embedding.request_count,
        "total": (probe_adapter.request_count + first_adapter_request_count +
                  reopened_memory.embedding.request_count),
    }
    complete_checkpoint("verified reopen, persistence, and second retrieval")
    artifact["status"] = "success"
    artifact["timestamp_completed_utc"] = datetime.now(timezone.utc).isoformat()
    save_artifact(artifact_path, artifact)
    return 0


def main():
    failure = None
    result = 1
    try:
        result = run_preflight()
    except Exception as exception:
        failure = exception
    finally:
        env = RUN_CONTEXT["env"]
        if env is not None:
            try:
                env.close()
            except Exception as close_exception:
                if failure is None:
                    failure = close_exception
                    set_stage("environment close")

    artifact = RUN_CONTEXT["artifact"]
    artifact_path = RUN_CONTEXT["artifact_path"]
    if failure is not None:
        if artifact is not None and artifact_path is not None:
            artifact["status"] = "failed"
            artifact["failure_stage"] = RUN_CONTEXT["failure_stage"]
            artifact["exception_type"] = type(failure).__name__
            artifact["exception_message"] = str(failure)
            artifact["completed_checkpoints"] = list(
                RUN_CONTEXT["completed_checkpoints"])
            save_artifact(artifact_path, artifact)
        raise failure

    print("artifact={}".format(artifact_path))
    return result


if __name__ == "__main__":
    sys.exit(main())
