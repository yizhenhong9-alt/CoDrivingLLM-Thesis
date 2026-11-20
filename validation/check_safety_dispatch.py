"""Check real helper dispatch with strict test doubles, without simulator/SDK imports."""

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SafetyDispatchTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls

        class Acceleration:
            def inference(self, vehicle, ego, env):
                calls.append(("acceleration", vehicle, ego, env))
                return "acceleration checked"

        class KeepSpeed:
            def inference(self, vehicle, ego):
                calls.append(("keep_speed", vehicle, ego))
                return "keep speed checked"

        class Deceleration:
            def inference(self, vehicle, ego):
                calls.append(("deceleration", vehicle, ego))
                return "deceleration checked"

        # Load the actual helper body without importing cloud/memory dependencies.
        source = (ROOT / "llm_controller" / "prompt_llm.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "check_safety_in_current_lane")
        namespace = {
            "isAccelerationConflictWithCar": Acceleration,
            "isKeepSpeedConflictWithCar": KeepSpeed,
            "isDecelerationSafe": Deceleration,
        }
        module = ast.Module(body=[helper], type_ignores=[])
        exec(compile(module, "<actual-safety-helper>", "exec"), namespace)
        self.helper = namespace[helper.name]
        self.tools = [Acceleration(), KeepSpeed(), Deceleration()]
        self.vehicle, self.ego, self.env = object(), object(), object()

    def run_helper(self, leading=None, rearing=None):
        return self.helper(
            self.tools, {"lane": {"leadingCar": leading, "rearingCar": rearing}},
            {"currentLaneID": "lane"}, self.ego, self.env,
        )

    def test_leading_vehicle_receives_same_env(self):
        result = self.run_helper(leading=self.vehicle)
        self.assertEqual(self.calls, [
            ("acceleration", self.vehicle, self.ego, self.env),
            ("keep_speed", self.vehicle, self.ego),
        ])
        self.assertEqual(result["acceleration_conflict"], "acceleration checked")
        self.assertIsNone(result["deceleration_conflict"])

    def test_rearing_vehicle_keeps_original_signatures(self):
        result = self.run_helper(rearing=self.vehicle)
        self.assertEqual(self.calls, [
            ("keep_speed", self.vehicle, self.ego),
            ("deceleration", self.vehicle, self.ego),
        ])
        self.assertIsNone(result["acceleration_conflict"])

    def test_empty_lane_does_not_invent_safety_results(self):
        result = self.run_helper()
        self.assertEqual(self.calls, [])
        self.assertTrue(all(value is None for value in result.values()))

    def test_action_builder_passes_env_to_helper(self):
        source = (ROOT / "llm_controller" / "llm_agent_action.py").read_text(encoding="utf-8")
        calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "check_safety_in_current_lane"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0].args), 5)
        self.assertIsInstance(calls[0].args[-1], ast.Name)
        self.assertEqual(calls[0].args[-1].id, "env")


if __name__ == "__main__":
    unittest.main(verbosity=2)
