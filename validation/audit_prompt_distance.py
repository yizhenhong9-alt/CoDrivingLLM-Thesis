"""M13: reproduce the original lane helper's signed distance, no changes.

Standard library only. Executes the original helper body using saved scene
coordinates and a reconstructed destination; no model or simulator imports.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class Car:
    def __init__(self, position, destination, label, speed):
        self.position, self.destination, self.label, self.speed = position, destination, label, speed
        self.lane_index = ("o0", "ir0", 0)

    def __str__(self):
        return self.label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traffic-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.traffic_json.read_bytes()
    traffic = json.loads(raw.decode("utf-8-sig"))
    source = ROOT / "llm_controller/prompt_llm.py"
    code = source.read_bytes()
    tree = ast.parse(code.decode("utf-8-sig"))
    which_lane = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "which_lane")
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "getLaneInvolvedCar")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "inference")
    method.decorator_list = []  # Remove registration metadata only, retain original method body.
    namespace = {"np": SimpleNamespace(sqrt=math.sqrt), "re": re}
    exec(compile(ast.Module(body=[which_lane, method], type_ignores=[]), str(source), "exec"), namespace)
    ego_state = next(vehicle for vehicle in traffic["initial_vehicles"] if vehicle["id"] == 3)
    action = next(call for call in traffic["calls"] if call["stage"] == "action" and call["context"]["vehicle_id"] == 3)
    text = action["messages"][0]["content"]
    match = re.search(r"(IDMVehicle #[0-9]+): \[\s*([-0-9.]+)\s+([-0-9.]+)\] is driving at ([0-9.]+)m/s", text)
    if not match:
        raise ValueError("Cannot find saved leading-car coordinates in this M10 prompt")
    label, x, y, speed = match.groups()
    # From original _make_road: lane_width=4, outer_distance=11, access_length=100;
    # vehicle 3's last route lane il1 -> o1 ends at (-111, -2).
    if ego_state["route"][-1][:2] != ["il1", "o1"]:
        raise ValueError("Audit reconstruction is only for this documented route")
    destination = (-111.0, -2.0)
    ego = Car(tuple(ego_state["position"]), destination, "ego simulation ID 3", ego_state["speed_mps"])
    other = Car((float(x), float(y)), destination, label, float(speed))
    road = SimpleNamespace(vehicles=[ego, other])
    env = SimpleNamespace(spec=SimpleNamespace(id="intersection-multi-agent-v0"))
    leading, rear, generated = namespace["inference"](None, str(ego.lane_index), ego, road, env)
    def distance(left, right):
        return math.sqrt(sum((a-b)**2 for a, b in zip(left, right)))
    ego_to_destination = distance(ego.position, destination)
    other_to_destination = distance(other.position, destination)
    signed = other_to_destination-ego_to_destination
    report = dict(source_sha256=hashlib.sha256(code).hexdigest(),
        traffic_sha256=hashlib.sha256(raw).hexdigest(),
        input_precision="ego from snapshot; other from rounded position in original prompt",
        destination_evidence="Reconstructed from original road construction and saved ego route, not a recorded runtime field",
        reconstructed_destination=destination, ego_position=ego.position, other_position=other.position,
        ego_to_destination_m=ego_to_destination, other_to_ego_destination_m=other_to_destination,
        original_signed_difference_m=signed, absolute_difference_m=abs(signed),
        center_to_center_euclidean_m=distance(ego.position, other.position),
        leading_car_selected=leading is other, rear_car_selected=rear is other,
        generated_original_text=generated, saved_prompt_contains_minus_6_59="-6.59 meters" in text,
        reproduced_minus_6_59=round(signed, 2) == -6.59 and "-6.59 meters" in generated,
        limitation="Center distance is not bumper clearance; no formula, priority or prompt changed")
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["reproduced_minus_6_59"] and leading is other else 1


if __name__ == "__main__":
    raise SystemExit(main())
