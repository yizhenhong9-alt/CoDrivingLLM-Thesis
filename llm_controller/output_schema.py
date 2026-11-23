"""Strict JSON parsing for the Qwen path (Python 3.8 compatible syntax).

This module performs no model calls or simulation changes. Vehicle IDs must come
from the caller's current episode mapping, never from object display strings.
"""

import json
from .action_config import actions_for_scene


INTERSECTION_ACTIONS = actions_for_scene("intersection")


class OutputValidationError(ValueError):
    """A model response must not be passed to env.step."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OutputValidationError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _object(text, fields):
    if not isinstance(text, str):
        raise OutputValidationError("Response must be JSON text")
    try:
        data = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, TypeError) as exc:
        raise OutputValidationError("Invalid JSON: " + str(exc)) from exc
    if not isinstance(data, dict) or set(data) != set(fields):
        raise OutputValidationError("Unexpected or missing JSON fields")
    return data


def _vehicle_id(value):
    if type(value) is not int or value < 0:
        raise OutputValidationError("Vehicle ID must be a nonnegative integer")
    return value


def parse_action(text, expected_vehicle_id, available_actions, *, scene):
    """Return {vehicle_id, decision, action_id}; reject ambiguous responses.

    available_actions is the current vehicle's available action names, obtained
    by the caller from the simulator. It must not be inferred from the response.
    """
    _vehicle_id(expected_vehicle_id)
    mapping = actions_for_scene(scene)
    available = tuple(available_actions)
    if not available or any(name not in mapping for name in available):
        raise OutputValidationError("Invalid available action names")
    data = _object(text, ("vehicle_id", "decision"))
    if _vehicle_id(data["vehicle_id"]) != expected_vehicle_id:
        raise OutputValidationError("Response belongs to another vehicle")
    decision = data["decision"]
    if not isinstance(decision, str) or decision not in available:
        raise OutputValidationError("Decision is not an available action")
    return dict(data, action_id=mapping[decision])


def parse_negotiation(text, expected_pairs):
    """Validate one passing order per supplied conflict pair, without choosing it.

    Pair orientation is irrelevant. This checks completeness and identity only;
    it does not change priority rules or resolve multi-vehicle ordering cycles.
    """
    expected = set()
    for pair in expected_pairs:
        if len(pair) != 2:
            raise OutputValidationError("Conflict pair must contain two IDs")
        first, second = (_vehicle_id(value) for value in pair)
        key = frozenset((first, second))
        if first == second or key in expected:
            raise OutputValidationError("Self or duplicate input conflict pair")
        expected.add(key)
    data = _object(text, ("decisions",))
    if not isinstance(data["decisions"], list):
        raise OutputValidationError("decisions must be a list")
    seen = set()
    for decision in data["decisions"]:
        if not isinstance(decision, dict) or set(decision) != {"first_vehicle", "second_vehicle"}:
            raise OutputValidationError("Invalid passing-order fields")
        first = _vehicle_id(decision["first_vehicle"])
        second = _vehicle_id(decision["second_vehicle"])
        key = frozenset((first, second))
        if first == second or key not in expected or key in seen:
            raise OutputValidationError("Unknown, self or duplicate conflict pair")
        seen.add(key)
    if seen != expected:
        raise OutputValidationError("Missing conflict decisions")
    return data["decisions"]
