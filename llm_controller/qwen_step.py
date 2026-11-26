"""One-step intersection orchestration, with no SDK or simulator imports.

The caller supplies original agents. Original safety helpers and the 5 m/s
clamp remain in use. Fixtures are never applied to traffic.
"""
import json
import re
import time
from .action_config import actions_for_scene
from .memory_mode import create_memory
from .output_schema import OutputValidationError, parse_action, parse_negotiation
from .vehicle_actions import EpisodeVehicleMap

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8"


def _comparison(function):
    try:
        return {"status": "parsed", "value": function()}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _legacy_orders(agent, raw, vehicles, pairs, names):
    found = []
    for vehicle in vehicles:
        for first, second, order in agent.extract_vehicle_conflicts(raw, names[vehicle.id]):
            if order == "first":
                reverse = {name: vehicle_id for vehicle_id, name in names.items()}
                found.append({"first_vehicle": reverse[first], "second_vehicle": reverse[second]})
    matched = re.findall(r'"first_vehicle": "(?:MDPVehicle #[0-9]+|IDMVehicle #[0-9]+)", "second_vehicle": "(?:MDPVehicle #[0-9]+|IDMVehicle #[0-9]+)"', raw)
    if len(matched) != len(found):
        raise OutputValidationError("Unknown legacy vehicle label")
    return parse_negotiation(json.dumps({"decisions": found}), pairs)


def run_step(env, negotiation, action, transport, report, *, parser_mode,
             episode_id, apply_step=False, persist=lambda report: None, step_id=0,
             memory_prompt=None):
    if parser_mode not in ("legacy", "strict"):
        raise ValueError("Unknown parser mode")
    if apply_step and transport.mode != "live":
        raise ValueError("Fixture responses must not be applied to traffic")
    if memory_prompt is not None:
        from .original_memory import OriginalMemorySession
        original_memory = isinstance(memory_prompt, OriginalMemorySession)
        if original_memory and (not memory_prompt.active or
                (transport.mode == 'fixture' and not memory_prompt.config['test_only'])):
            raise ValueError('Active original session required; fixtures may write only test-only stores')
        if apply_step and not original_memory:
            raise ValueError('Memory retrieval integration is zero-step pending validation')
        if transport.mode != 'fixture':
            from .memory_session import OnlineMemorySession
            if not isinstance(memory_prompt, OnlineMemorySession) or not memory_prompt.active:
                raise ValueError('Live zero-step memory requires an active configured session')
    if env.spec.id != "intersection-multi-agent-v0":
        raise ValueError("M05 runtime currently supports intersection only")
    if create_memory(env, "off") is not None:
        raise RuntimeError("Memory must be off")
    mapping = EpisodeVehicleMap(episode_id, env.road.vehicles)
    vehicles = tuple(env.controlled_vehicles)
    names = {mapping.vehicle_id(v): str(v).split(":")[0].strip() for v in env.road.vehicles}
    report['vehicle_identifiers'] = [
        {'simulation_id': key, 'legacy_label': value} for key, value in names.items()]
    if len(set(names.values())) != len(names):
        report['legacy_label_collisions'] = [
            dict(legacy_label=label, vehicles=[dict(simulation_id=mapping.vehicle_id(v),
                 python_object_id=id(v), modulo_1000=id(v) % 1000)
                 for v in env.road.vehicles if names[mapping.vehicle_id(v)] == label])
            for label in sorted(set(names.values())) if list(names.values()).count(label) > 1]
        persist(report)
        raise OutputValidationError("Original safety-helper labels collided")
    report.update(model=MODEL, mode=transport.mode, parser_mode=parser_mode,
                  prompt_version="M05-" + parser_mode, memory_mode="off",
                  environment_steps=0, calls=[], vehicle_identifiers=[
                      {"simulation_id": key, "legacy_label": value} for key, value in names.items()],
                  limitation="Safety formulas/priority unchanged; fixture is not a driving policy")
    if memory_prompt is not None:
        report.update(memory_mode=getattr(memory_prompt, 'mode', 'retrieval-only-fixture'), prompt_version='M21-R1-'+parser_mode,
                      memory_queries=[])
        if getattr(memory_prompt, 'mode', None) == 'retrieve-only':
            report['prompt_version'] = 'M21-R4-'+parser_mode
        if getattr(memory_prompt, 'mode', None) == 'on':
            report.update(prompt_version='M22-original-'+parser_mode, memory_updates=[])

    def request(stage, prompt, context):
        entry = {"stage": stage, "messages": [{"role": "system", "content": prompt}],
                 "context": context, "sent_to_model": transport.mode == "live"}
        report["calls"].append(entry)
        if memory_prompt is not None and hasattr(memory_prompt, 'check_request'):
            entry['token_budget'] = memory_prompt.check_request(entry['messages'], stage)
        persist(report)
        started = time.perf_counter()
        try:
            raw = transport.complete(entry["messages"], stage, context)
            entry["raw_response"] = raw
            return raw, entry
        except Exception as exc:
            entry["error"] = str(exc)
            raise
        finally:
            entry["wall_seconds"] = time.perf_counter() - started
            if transport.mode == "live":
                entry["api_response"] = transport.last_response
            persist(report)

    conflicts = negotiation.detect_conflicts(env)
    groups, pairs = [], []
    for i, vehicle in enumerate(vehicles):
        for other in vehicles[:i]:
            if other in conflicts[vehicle] and vehicle in conflicts[other]:
                groups.append({"vehicle_i": vehicle, "vehicle_i speed": vehicle.speed,
                               "vehicle_i distance to conflict": conflicts[vehicle][other],
                               "vehicle_j": other, "vehicle_j speed": other.speed,
                               "vehicle_j distance to conflict": conflicts[other][vehicle]})
                pairs.append((mapping.vehicle_id(vehicle), mapping.vehicle_id(other)))
    text = "\n".join(
        "- Vehicle i: {}, Vehicle i Speed: {} m/s, Vehicle i distance to conflict point: {} meters, "
        "- Vehicle j: {}, Vehicle j Speed: {} m/s, Vehicle j distance to conflict point: {} meters".format(
            g["vehicle_i"], g["vehicle_i speed"], g["vehicle_i distance to conflict"],
            g["vehicle_j"], g["vehicle_j speed"], g["vehicle_j distance to conflict"])
        for g in groups)
    prompt = ("You are simulating as a traffic police officer overseeing traffic conflicts. "
              "Here are the current conflict scenarios:\n" + text +
              "\nFor each conflict, decide which vehicle should pass first and which should pass later to ensure safety.\n")
    if parser_mode == "strict":
        prompt += ("Return only JSON: {\"decisions\":[{\"first_vehicle\":3,\"second_vehicle\":4}]}. "
                   "Use integer simulation IDs from the mapping, one order per listed pair; "
                   "no conflicts means an empty decisions list.\nMapping: " + json.dumps(names) +
                   "\nPairs: " + json.dumps(pairs))
    else:
        prompt += ('Output Final Answer followed by "decisions": ['
                   '{"first_vehicle": "<vehicle_i>", "second_vehicle": "<vehicle_j>"}]. '
                   'Use the original vehicle labels, with this exact field order and spacing.')
    raw, entry = request("negotiation", prompt, {"pairs": pairs, "names": names})
    entry["parsers"] = {
        "legacy": _comparison(lambda: _legacy_orders(action, raw, vehicles, pairs, names)),
        "strict": _comparison(lambda: parse_negotiation(raw, pairs)),
    }
    selected = entry["parsers"][parser_mode]
    persist(report)
    if selected["status"] != "parsed":
        raise OutputValidationError("Negotiation rejected: " + selected["error"])
    # Keep the original helper's label/regex input, without changing its policy.
    bridge = json.dumps({"decisions": [
        {"first_vehicle": names[d["first_vehicle"]], "second_vehicle": names[d["second_vehicle"]]}
        for d in selected["value"]]})
    available, execution = {}, actions_for_scene("intersection")
    controllers = env.action_type.agents_action_types
    if len(controllers) != len(vehicles):
        raise OutputValidationError("Action controller count mismatch")
    for vehicle, controller in zip(vehicles, controllers):
        if controller.controlled_vehicle is not vehicle:
            raise OutputValidationError("Action controller vehicle mismatch")
        if controller.actions != {value: key for key, value in execution.items()}:
            raise OutputValidationError("Execution mapping differs from configured IDs")
        ids = action.toolModels[0]._get_available_actions1(vehicle, env, True)
        if not ids or any(value not in controller.actions for value in ids):
            raise OutputValidationError("Invalid simulator available actions")
        available[vehicle.id] = [controller.actions[value] for value in ids]
    batch = mapping.step(step_id, vehicles, available, scene="intersection")
    report["available_actions"] = available
    for vehicle in vehicles:
        # Original action module applies this clamp before building each prompt.
        vehicle.speed = min(vehicle.speed, 5)
        orders = action.transfer_negotiation_prompts_to_results(vehicle, bridge)
        scenario = action.prompt_engineer(vehicle, env.road, env, orders, groups)
        pre = action.pre_prompt
        prompt = (pre.SYSTEM_MESSAGE_PREFIX_intersection.replace(
            "You are ChatGPT, a large language model trained by OpenAI.",
            "You are a driving assistant.") +
            "\nCurrent scenario:\n" + scenario + "\nRules:\n" + pre.get_traffic_rules(True) +
            "\nAttention points:\n" + pre.get_decision_cautions(True) +
            "\nConflicts and suggested passing orders (when suggested to pass second, better to slow down):\n" + orders)
        if parser_mode == "strict":
            prompt += ('\nReturn only JSON with exactly vehicle_id and decision, for example '
                       '{"vehicle_id":' + str(vehicle.id) + ',"decision":"IDLE"}.')
        else:
            prompt += '\nOutput Final Answer: "decision": {"<ONE available action>"}'
        prompt += "\nYour simulation vehicle ID: {}. Available actions: {}".format(
            vehicle.id, json.dumps(available[vehicle.id]))
        if memory_prompt is not None:
            prompt, memory_receipt = memory_prompt.prepare(scenario, prompt)
            report['memory_queries'].append(dict(vehicle_id=vehicle.id, **memory_receipt))
            persist(report)
        raw, entry = request("action", prompt, {"vehicle_id": vehicle.id,
                                               "available_actions": available[vehicle.id]})

        def legacy_action():
            decision = action.extract_decision(raw)
            # Original parsing is preserved; submission checks still reject -1,
            # unknown actions and actions unavailable for this vehicle.
            return parse_action(json.dumps({"vehicle_id": vehicle.id, "decision": decision}),
                                vehicle.id, available[vehicle.id], scene="intersection")

        entry["parsers"] = {
            "legacy": _comparison(legacy_action),
            "strict": _comparison(lambda: parse_action(raw, vehicle.id, available[vehicle.id],
                                                        scene="intersection")),
        }
        selected = entry["parsers"][parser_mode]
        persist(report)
        if selected["status"] != "parsed":
            raise OutputValidationError("Action rejected: " + selected["error"])
        batch.add(json.dumps({key: selected["value"][key] for key in ("vehicle_id", "decision")}),
                  episode_id=episode_id, step_id=step_id, expected_vehicle_id=vehicle.id)
        if memory_prompt is not None and getattr(memory_prompt, 'mode', None) == 'on':
            update = memory_prompt.make_update(action, scenario, selected['value']['action_id'],
                episode_id=episode_id, step_id=step_id, vehicle_id=vehicle.id,
                code_commit=report.get('git_commit', 'unavailable'))
            report['memory_updates'].append(update)
            persist(report)
            try:
                memory_prompt.commit_update(update)
            finally:
                persist(report)
    result = batch.finalize(env.controlled_vehicles)
    report["validated_actions"] = result
    report["status"] = "validated_not_applied"
    persist(report)
    if apply_step:
        report["submitted_vehicle_actions"] = [
            {"vehicle_id": vehicle_id, "action_id": action_id}
            for vehicle_id, action_id in zip(batch.ids, result)]
        report["step_attempted"] = True
        persist(report)
        before_ticks = getattr(env, "time", None)
        _, reward, done, info = env.step(result, env)
        after_ticks = getattr(env, "time", None)
        frequency = getattr(env, "config", {}).get("simulation_frequency")
        ticks = after_ticks-before_ticks if before_ticks is not None and after_ticks is not None else None
        report["step_observation"] = dict(
            physics_ticks=ticks,
            simulated_seconds=ticks/frequency if ticks is not None and frequency else None,
            safety_guarantee=getattr(env, "config", {}).get("safety_guarantee"),
            environment_action=getattr(env, "new_action", None))
        report.update(environment_steps=1, reward=reward, done=bool(done), info=info,
                      status="single_step_complete")
        persist(report)
    return result
