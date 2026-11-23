"""Characterize actual original parser methods without cloud/simulator imports.

Assertions deliberately describe observed legacy behavior, including defects.
Passing these tests means reproduction succeeded, not that parsing is correct.
"""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "llm_controller/llm_agent_action.py"
RAW = SOURCE.read_bytes()
TREE = ast.parse(RAW.decode("utf-8-sig"))
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
             and node.name == "LlmAgent_action_module")
METHODS = [node for node in CLASS.body if isinstance(node, ast.FunctionDef)
           and node.name in {"extract_decision", "extract_vehicle_conflicts"}]
NAMESPACE = {"re": re}
exec(compile(ast.Module(body=METHODS, type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)
AGENT = SimpleNamespace(is_intersection=True)
PAIR = {"first_vehicle": "MDPVehicle #3", "second_vehicle": "MDPVehicle #4"}
CASES = []


class OriginalParserReproduction(unittest.TestCase):
    def action(self, case, text, observed, concern):
        actual = NAMESPACE["extract_decision"](AGENT, text)
        CASES.append(dict(case=case, input=text, actual=actual, concern=concern))
        self.assertEqual(actual, observed)

    def negotiation(self, case, text, observed, concern):
        # These variants all parse to the same data with the standard JSON reader.
        self.assertEqual(json.loads(text), {"decisions": [PAIR]})
        actual = NAMESPACE["extract_vehicle_conflicts"](AGENT, text, "MDPVehicle #3")
        CASES.append(dict(case=case, input=text, actual=actual, concern=concern))
        self.assertEqual(actual, observed)

    def test_original_action_example(self):
        self.action("legacy_action", '"decision": {"IDLE"}', "IDLE",
                    "Original prompt format works, although it is not valid JSON")

    def test_negated_action_is_accepted(self):
        self.action("negated_action", '"decision": {"NOT IDLE"}', "IDLE",
                    "Negated action is silently accepted as IDLE")

    def test_multiple_actions_choose_faster(self):
        self.action("ambiguous_action", '"decision": {"IDLE or FASTER"}', "FASTER",
                    "Ambiguous alternatives silently choose FASTER by branch order")

    def test_wrong_field_is_accepted(self):
        self.action("missing_decision", '{"comment":"FASTER"}', "FASTER",
                    "Missing decision field still produces an action")

    def test_plain_json_action(self):
        self.action("plain_json_action", '{"decision":"IDLE"}', 'IDLE',
                    "This valid JSON example works through keyword matching")

    def test_original_negotiation_spacing(self):
        self.negotiation("legacy_spacing", json.dumps({"decisions": [PAIR]}),
                         [("MDPVehicle #3", "MDPVehicle #4", "first")],
                         "Original spacing and field order work")

    def test_compact_negotiation_lost(self):
        self.negotiation("compact_json", json.dumps({"decisions": [PAIR]}, separators=(",", ":")),
                         [], "Equivalent compact JSON silently loses the decision")

    def test_pretty_negotiation_lost(self):
        self.negotiation("pretty_json", json.dumps({"decisions": [PAIR]}, indent=2),
                         [], "Equivalent multiline JSON silently loses the decision")

    def test_reordered_fields_lost(self):
        reversed_pair = {"second_vehicle": "MDPVehicle #4", "first_vehicle": "MDPVehicle #3"}
        self.negotiation("reordered_fields", json.dumps({"decisions": [reversed_pair]}),
                         [], "Equivalent field reordering silently loses the decision")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OriginalParserReproduction))
    report = {
        "purpose": "Reproduce original behavior; passing does not mean correct parsing",
        "source": "llm_controller/llm_agent_action.py",
        "source_sha256": hashlib.sha256(RAW).hexdigest(),
        "python": sys.version,
        "execution": "Local offline method-body execution via AST; no agent constructor or imports",
        "model_calls": 0, "environment_steps": 0,
        "tests_run": result.testsRun, "reproduction_passed": result.wasSuccessful(),
        "cases": CASES,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
