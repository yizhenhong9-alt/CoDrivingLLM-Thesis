"""M05 standard-library flow tests, with fake environment and transport."""
import ast
import json
import hashlib
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.qwen_step import MODEL, run_step
from llm_controller.qwen_transport import FixtureReplies, LocalQwen
from llm_controller.output_schema import OutputValidationError


class Vehicle:
    def __init__(self, number):
        self.id, self.speed = number, 7

    def __str__(self):
        return "MDPVehicle #{}: [0 0]".format(self.id)


def original_methods():
    tree = ast.parse((ROOT / "llm_controller/llm_agent_action.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "LlmAgent_action_module")
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in
               ("extract_decision", "extract_vehicle_conflicts", "transfer_negotiation_prompts_to_results")]
    scope = {"re": re}
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<actual-methods>", "exec"), scope)
    return scope


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.cars = [Vehicle(3), Vehicle(4)]
        self.steps = []
        self.env = SimpleNamespace(spec=SimpleNamespace(id="intersection-multi-agent-v0"),
            road=SimpleNamespace(vehicles=self.cars), controlled_vehicles=self.cars,
            action_type=SimpleNamespace(agents_action_types=[
                SimpleNamespace(controlled_vehicle=v, actions={1: "IDLE", 3: "FASTER", 4: "SLOWER"})
                for v in self.cars]), step=self.step)
        self.negotiation = SimpleNamespace(detect_conflicts=lambda env: {
            self.cars[0]: {self.cars[1]: 10}, self.cars[1]: {self.cars[0]: 12}})
        self.action = SimpleNamespace(is_intersection=True,
            toolModels=[SimpleNamespace(_get_available_actions1=lambda *args: [1, 3, 4])],
            prompt_engineer=lambda *args: "Original safety-tool text (test double)",
            pre_prompt=SimpleNamespace(SYSTEM_MESSAGE_PREFIX_intersection="driving assistant",
                get_traffic_rules=lambda flag: "rules", get_decision_cautions=lambda flag: "priority"))
        for name, method in original_methods().items():
            if callable(method) and name in ("extract_decision", "extract_vehicle_conflicts",
                                            "transfer_negotiation_prompts_to_results"):
                setattr(self.action, name, method.__get__(self.action))
        self.report, self.saved = {}, []

    def step(self, actions, env):
        self.steps.append(actions)
        return None, 1, False, {}

    def run_flow(self, transport, mode="strict", apply=False):
        return run_step(self.env, self.negotiation, self.action, transport, self.report,
                        parser_mode=mode, episode_id="offline-test", apply_step=apply,
                        persist=lambda report: self.saved.append(json.loads(json.dumps(report))))

    def test_strict_fixture_validates_but_never_steps(self):
        self.assertEqual(self.run_flow(FixtureReplies("strict")), (1, 1))
        self.assertEqual(self.steps, [])
        self.assertEqual(len(self.report["calls"]), 3)
        self.assertEqual([v.speed for v in self.cars], [5, 5])
        self.assertTrue(all(c["sent_to_model"] is False for c in self.report["calls"]))

    def test_legacy_parser_uses_actual_original_methods(self):
        self.assertEqual(self.run_flow(FixtureReplies("legacy"), "legacy"), (1, 1))
        self.assertEqual(self.steps, [])
        self.assertEqual(self.report["calls"][0]["parsers"]["legacy"]["status"], "parsed")
        self.assertEqual(self.report["calls"][0]["parsers"]["strict"]["status"], "rejected")

    def test_fixture_cannot_be_applied(self):
        with self.assertRaises(ValueError):
            self.run_flow(FixtureReplies("strict"), apply=True)
        self.assertEqual(self.steps, [])

    def test_live_test_double_steps_once_after_validation_saved(self):
        # No network: mode flag only emulates a completed live request.
        transport = FixtureReplies("strict")
        transport.mode, transport.last_response = "live", {"test_double": True}
        self.assertEqual(self.run_flow(transport, apply=True), (1, 1))
        self.assertEqual(self.steps, [(1, 1)])
        self.assertEqual(self.report["submitted_vehicle_actions"], [
            {"vehicle_id":3,"action_id":1}, {"vehicle_id":4,"action_id":1}])
        self.assertTrue(any(s.get("status") == "validated_not_applied" for s in self.saved))

    def test_invalid_action_blocks_step_and_keeps_raw(self):
        transport = FixtureReplies("strict")
        transport.mode, transport.last_response = "live", None
        normal = transport.complete
        transport.complete = lambda messages, stage, context: (
            '{"vehicle_id":99,"decision":"FASTER"}' if stage == "action"
            else normal(messages, stage, context))
        with self.assertRaises(OutputValidationError):
            self.run_flow(transport, apply=True)
        self.assertEqual(self.steps, [])
        self.assertIn("99", self.report["calls"][-1]["raw_response"])

    def test_step_records_ticks_and_environment_action_separately(self):
        self.env.time = 20
        self.env.config = {"simulation_frequency":20,"safety_guarantee":True}
        def step(actions, env):
            self.steps.append(actions)
            env.time += 4
            env.new_action = (4, 1)  # Test double, not an actual safety policy.
            return None, 1, False, {}
        self.env.step = step
        transport = FixtureReplies("strict")
        transport.mode, transport.last_response = "live", None
        self.run_flow(transport, apply=True)
        self.assertEqual(self.steps, [(1, 1)])
        self.assertEqual(self.report["step_observation"], dict(physics_ticks=4,
            simulated_seconds=0.2, safety_guarantee=True, environment_action=(4, 1)))

    def test_missing_negotiation_blocks_action_calls(self):
        transport = FixtureReplies("strict")
        transport.complete = lambda *args: '{"decisions":[]}'
        with self.assertRaises(OutputValidationError):
            self.run_flow(transport)
        self.assertEqual(len(self.report["calls"]), 1)
        self.assertEqual(self.steps, [])

    def test_timeout_is_not_retried_or_replaced_with_idle(self):
        transport = FixtureReplies("strict")
        def fail(*args):
            raise TimeoutError("offline timeout")
        transport.complete = fail
        with self.assertRaises(TimeoutError):
            self.run_flow(transport)
        self.assertEqual(len(self.report["calls"]), 1)
        self.assertEqual(self.steps, [])
        self.assertIn("timeout", self.report["calls"][0]["error"])

    def test_wrong_execution_mapping_is_rejected(self):
        self.env.action_type.agents_action_types[0].actions = {0: "SLOWER", 1: "IDLE", 2: "FASTER"}
        with self.assertRaises(OutputValidationError):
            self.run_flow(FixtureReplies("strict"))
        self.assertEqual(self.steps, [])


class TransportTests(unittest.TestCase):
    def test_source_hash_record_accepts_relative_script_path(self):
        script = ROOT / "validation/run_qwen_single_step.py"
        tree = ast.parse(script.read_text(encoding="utf-8"))
        assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and isinstance(node.value, ast.DictComp))
        scope = {"ROOT": ROOT, "Path": Path, "hashlib": hashlib, "report": {},
                 "__file__": os.path.relpath(str(script), os.getcwd())}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), "<actual-provenance>", "exec"), scope)
        self.assertEqual(scope["report"]["source_sha256"][str(script.relative_to(ROOT))],
                         hashlib.sha256(script.read_bytes()).hexdigest())

    def test_python38_syntax(self):
        for name in ("llm_controller/qwen_step.py", "llm_controller/qwen_transport.py",
                     "validation/run_qwen_single_step.py"):
            ast.parse((ROOT / name).read_text(encoding="utf-8"), feature_version=(3, 8))

    def test_fixed_model_and_loopback(self):
        transport = LocalQwen()
        fake = {"choices": [{"finish_reason": "stop", "message": {"content": "2"}}]}
        with patch.object(transport, "_request", return_value=fake) as request:
            self.assertEqual(transport.complete([], "action", {}), "2")
        self.assertEqual(request.call_args[0][1]["model"], MODEL)
        self.assertEqual(transport.base, "http://127.0.0.1:18080/v1")

    def test_incomplete_response_rejected_but_retained(self):
        transport = LocalQwen()
        fake = {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}
        with patch.object(transport, "_request", return_value=fake):
            with self.assertRaises(RuntimeError):
                transport.complete([], "action", {})
        self.assertEqual(transport.last_response, fake)

    def test_wrong_model_preflight(self):
        transport = LocalQwen()
        with patch.object(transport, "_request", return_value={"data": [{"id": "other"}]}):
            with self.assertRaises(RuntimeError):
                transport.preflight()


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
