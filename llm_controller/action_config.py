"""Scene action names, preserving the original execution IDs."""


def actions_for_scene(scene):
    longitudinal = {"IDLE": 1, "FASTER": 3, "SLOWER": 4}
    if scene in ("intersection", "merge"):
        return longitudinal
    if scene == "highway":
        return dict(longitudinal, LANE_LEFT=0, LANE_RIGHT=2)
    raise ValueError("Unsupported scene: " + str(scene))
