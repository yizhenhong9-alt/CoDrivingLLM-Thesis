"""Offline output parser tests; standard library only, no model/simulator imports."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_controller.output_schema import (
    INTERSECTION_ACTIONS, OutputValidationError, parse_action, parse_negotiation,
)


class OutputSchemaTest(unittest.TestCase):
    def test_action_mapping(self):
        for name, number in (("IDLE", 1), ("FASTER", 3), ("SLOWER", 4)):
            with self.subTest(name=name):
                result = parse_action('{"decision":"%s","vehicle_id":3}' % name,
                                      3, INTERSECTION_ACTIONS, scene="intersection")
                self.assertEqual(result["action_id"], number)

    def test_invalid_actions(self):
        responses = [
            '{"vehicle_id":3,"decision":"LANE_LEFT"}',
            '{"vehicle_id":3,"decision":"NOT IDLE"}',
            '{"vehicle_id":3,"decision":"IDLE or FASTER"}',
            '{"vehicle_id":3,"decision":"idle"}',
            '{"vehicle_id":3,"decision":["IDLE"]}',
            '{"vehicle_id":4,"decision":"IDLE"}',
            '{"vehicle_id":true,"decision":"IDLE"}',
            '{"vehicle_id":3.0,"decision":"IDLE"}',
            '{"decision":"IDLE"}',
            '{"vehicle_id":3,"decision":"IDLE","extra":1}',
            '{"vehicle_id":3,"decision":"FASTER","decision":"IDLE"}',
            '```json\n{"vehicle_id":3,"decision":"IDLE"}\n```',
            'Final Answer: {"vehicle_id":3,"decision":"IDLE"}',
            '{"vehicle_id":3,"decision":{"IDLE"}}',
            '', None,
        ]
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaises(OutputValidationError):
                    parse_action(response, 3, INTERSECTION_ACTIONS, scene="intersection")

    def test_current_availability(self):
        with self.assertRaises(OutputValidationError):
            parse_action('{"vehicle_id":3,"decision":"FASTER"}', 3, ["IDLE", "SLOWER"], scene="intersection")

    def test_negotiation_whitespace_and_order(self):
        result = parse_negotiation(
            '{ "decisions": [ {"second_vehicle": 3, "first_vehicle": 4} ] }', [(3, 4)])
        self.assertEqual(result, [{"first_vehicle": 4, "second_vehicle": 3}])

    def test_empty_conflicts(self):
        self.assertEqual(parse_negotiation('{"decisions":[]}', []), [])

    def test_invalid_negotiation(self):
        responses = [
            '{"decisions":[]}', '{"decisions":{}}',
            '{"decisions":[{"first_vehicle":3,"second_vehicle":3}]}',
            '{"decisions":[{"first_vehicle":3,"second_vehicle":5}]}',
            '{"decisions":[{"first_vehicle":3}]}',
            '{"decisions":[{"first_vehicle":"3","second_vehicle":4}]}',
            '{"decisions":[{"first_vehicle":3,"second_vehicle":4},'
            '{"first_vehicle":4,"second_vehicle":3}]}',
        ]
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaises(OutputValidationError):
                    parse_negotiation(response, [(3, 4)])

    def test_multiple_pairs_require_complete_coverage(self):
        with self.assertRaises(OutputValidationError):
            parse_negotiation('{"decisions":[{"first_vehicle":3,"second_vehicle":4}]}',
                              [(3, 4), (3, 5)])


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
