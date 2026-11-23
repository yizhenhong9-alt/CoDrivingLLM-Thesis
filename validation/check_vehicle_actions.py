"""Offline M02/M03 tests, including original zip truncation reproduction."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_controller.action_config import actions_for_scene
from llm_controller.output_schema import OutputValidationError, parse_action
from llm_controller.vehicle_actions import EpisodeVehicleMap


class SceneTests(unittest.TestCase):
    def test_original_ids(self):
        for scene in ("intersection", "merge", "highway"):
            mapping = actions_for_scene(scene)
            for name, number in mapping.items():
                result = parse_action(json.dumps(dict(vehicle_id=3, decision=name)),
                                      3, mapping, scene=scene)
                self.assertEqual(result["action_id"], number)

    def test_scene_restrictions(self):
        for scene in ("intersection", "merge"):
            with self.assertRaises(OutputValidationError):
                parse_action('{"vehicle_id":3,"decision":"LANE_LEFT"}',
                             3, ["LANE_LEFT"], scene=scene)
        with self.assertRaises(ValueError):
            actions_for_scene("unknown")

    def test_returned_mapping_is_independent(self):
        mapping = actions_for_scene("intersection")
        mapping["IDLE"] = 99
        self.assertEqual(actions_for_scene("intersection")["IDLE"], 1)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.cars = [SimpleNamespace(id=3), SimpleNamespace(id=4)]
        self.mapping = EpisodeVehicleMap("episode-1", self.cars)
        self.batch = self.mapping.step(0, self.cars,
            {3: ["IDLE", "FASTER"], 4: ["IDLE", "SLOWER"]}, scene="intersection")

    def add(self, vehicle_id, decision="IDLE", **overrides):
        metadata = dict(episode_id="episode-1", step_id=0, expected_vehicle_id=vehicle_id)
        metadata.update(overrides)
        self.batch.add(json.dumps(dict(vehicle_id=vehicle_id, decision=decision)), **metadata)

    def test_out_of_order_replies(self):
        self.add(4, "SLOWER")
        self.add(3, "FASTER")
        self.assertEqual(self.batch.finalize(self.cars), (3, 4))

    def test_original_zip_truncates_missing_action(self):
        self.assertEqual(len(list(zip((1,), self.cars))), 1)
        self.add(3)
        with self.assertRaises(OutputValidationError):
            self.batch.finalize(self.cars)

    def test_duplicate_reply_blocks_entire_batch(self):
        self.add(3)
        with self.assertRaises(OutputValidationError):
            self.add(3)
        self.add(4)
        with self.assertRaises(OutputValidationError):
            self.batch.finalize(self.cars)

    def test_stale_metadata(self):
        for overrides in (dict(episode_id="episode-0"), dict(step_id=1)):
            with self.assertRaises(OutputValidationError):
                self.add(3, **overrides)

    def test_unknown_reply(self):
        with self.assertRaises(OutputValidationError):
            self.add(8)

    def test_wrong_vehicle_in_response(self):
        with self.assertRaises(OutputValidationError):
            self.batch.add('{"vehicle_id":4,"decision":"IDLE"}',
                           episode_id="episode-1", step_id=0, expected_vehicle_id=3)

    def test_changed_controlled_order(self):
        self.add(3)
        self.add(4)
        with self.assertRaises(OutputValidationError):
            self.batch.finalize(self.cars[::-1])

    def test_replaced_object_is_not_same_vehicle(self):
        with self.assertRaises(OutputValidationError):
            self.mapping.vehicle_id(SimpleNamespace(id=3))

    def test_duplicate_simulation_id(self):
        with self.assertRaises(OutputValidationError):
            EpisodeVehicleMap("episode-2", [SimpleNamespace(id=3), SimpleNamespace(id=3)])

    def test_invalid_reply_does_not_select_fallback(self):
        with self.assertRaises(OutputValidationError):
            self.add(3, "SLOWER")
        self.assertEqual(self.batch.results, {})


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
