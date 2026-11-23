"""Episode identity and per-step action checks; no simulator/cloud imports."""

from .output_schema import OutputValidationError, _vehicle_id, parse_action


class EpisodeVehicleMap:
    """Capture existing simulation IDs without changing vehicle objects.

    Construct after reset; recreate for each episode. New road vehicles must be
    registered by a future integration layer rather than guessed from labels.
    """

    def __init__(self, episode_id, vehicles):
        if not isinstance(episode_id, str) or not episode_id:
            raise OutputValidationError("Explicit episode ID required")
        self.episode_id = episode_id
        self._vehicles = {}
        for vehicle in vehicles:
            vehicle_id = _vehicle_id(getattr(vehicle, "id", None))
            if vehicle_id in self._vehicles:
                raise OutputValidationError("Duplicate simulation ID")
            self._vehicles[vehicle_id] = vehicle

    def vehicle_id(self, vehicle):
        vehicle_id = _vehicle_id(getattr(vehicle, "id", None))
        if self._vehicles.get(vehicle_id) is not vehicle:
            raise OutputValidationError("Unknown, replaced or stale vehicle")
        return vehicle_id

    def step(self, step_id, controlled_vehicles, available_actions, *, scene):
        return ActionBatch(self, step_id, controlled_vehicles, available_actions, scene)


class ActionBatch:
    """Collect replies by identity, then return a tuple in controlled-car order.

    Episode and step identifiers are caller-owned request metadata. They are not
    trusted fields supplied by the model. This class never calls env.step.
    """

    def __init__(self, mapping, step_id, vehicles, available_actions, scene):
        _vehicle_id(step_id)
        self.mapping, self.step_id, self.scene = mapping, step_id, scene
        self.vehicles = tuple(vehicles)
        self.ids = tuple(mapping.vehicle_id(vehicle) for vehicle in self.vehicles)
        if not self.ids or len(set(self.ids)) != len(self.ids):
            raise OutputValidationError("Empty or duplicate controlled vehicle list")
        if set(available_actions) != set(self.ids):
            raise OutputValidationError("Available action IDs do not match controlled vehicles")
        self.available = {key: tuple(value) for key, value in available_actions.items()}
        self.results = {}
        self.failed = False

    def add(self, text, *, episode_id, step_id, expected_vehicle_id):
        try:
            _vehicle_id(step_id)
            _vehicle_id(expected_vehicle_id)
            if (episode_id, step_id) != (self.mapping.episode_id, self.step_id):
                raise OutputValidationError("Reply belongs to another episode or step")
            if expected_vehicle_id not in self.ids or expected_vehicle_id in self.results:
                raise OutputValidationError("Unknown or duplicate vehicle reply")
            result = parse_action(text, expected_vehicle_id,
                                  self.available[expected_vehicle_id], scene=self.scene)
            self.results[expected_vehicle_id] = result["action_id"]
        except (ValueError, TypeError):
            self.failed = True
            raise

    def finalize(self, current_controlled_vehicles):
        current = tuple(current_controlled_vehicles)
        if self.failed or set(self.results) != set(self.ids):
            raise OutputValidationError("Failed or incomplete action batch")
        if len(current) != len(self.vehicles) or any(
                left is not right for left, right in zip(current, self.vehicles)):
            raise OutputValidationError("Controlled vehicle order changed during request")
        for vehicle in current:
            self.mapping.vehicle_id(vehicle)
        return tuple(self.results[vehicle_id] for vehicle_id in self.ids)
