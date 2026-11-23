"""M14 production entry and loop tests; no model, network or real simulator."""
import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.qwen_episode import run_episode, parser_counts, BudgetTransport, write_review
from llm_controller.qwen_transport import FixtureReplies
import check_qwen_single_step as step_checks
from run_qwen_live_session import traffic_args


class ProjectEntryTests(unittest.TestCase):
    def setup_flow(self, terminal_at=99):
        flow = step_checks.FlowTests()
        flow.setUp()
        flow.env.steps = 0
        def step(actions, env):
            env.steps += 1
            return None, 0, env.steps >= terminal_at, {}
        flow.env.step = step
        class FakeLive(FixtureReplies):
            mode = "live"
            last_response = None
        return flow, FakeLive("strict")

    def execute(self, folder, flow, transport, limit=3):
        summary = {}
        run_episode(flow.env, lambda env: flow.negotiation, lambda env: flow.action,
                    transport, Path(folder), parser_mode="strict", episode_id="test",
                    max_steps=limit, persist_summary=lambda value: None, summary=summary,
                    snapshot=lambda env: [])
        return summary

    def test_three_real_loop_iterations_stop_at_limit(self):
        flow, transport = self.setup_flow()
        with tempfile.TemporaryDirectory() as folder:
            summary = self.execute(folder, flow, transport)
            self.assertEqual(summary["status"], "step_limit_reached")
            self.assertEqual(flow.env.steps, 3)
            self.assertEqual(summary["parser_statistics"]["action"]["strict_parsed"], 6)
            for i in range(3):
                report = json.loads((Path(folder)/("step-%04d.json" % i)).read_text())
                self.assertEqual(report["step_id"], i)
                self.assertEqual(report["actual_environment_steps"], i+1)
                self.assertTrue(all("raw_response" in c for c in report["calls"]))
            write_review(Path(folder), summary)
            self.assertIn('Raw response', (Path(folder)/"review.md").read_text())

    def test_terminal_stops_without_extra_request(self):
        flow, transport = self.setup_flow(terminal_at=1)
        with tempfile.TemporaryDirectory() as folder:
            summary = self.execute(folder, flow, transport)
        self.assertEqual(summary["status"], "episode_terminal")
        self.assertEqual(flow.env.steps, 1)

    def test_second_step_bad_vehicle_stops_and_preserves_raw(self):
        flow, transport = self.setup_flow()
        original = transport.complete
        def complete(messages, stage, context):
            if flow.env.steps == 1 and stage == "action":
                return '{"vehicle_id":999,"decision":"IDLE"}'
            return original(messages, stage, context)
        transport.complete = complete
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.execute(folder, flow, transport)
            report = json.loads((Path(folder)/"step-0001.json").read_text())
        self.assertEqual(flow.env.steps, 1)
        self.assertEqual(report["status"], "failed")
        self.assertIn('999', report["calls"][-1]["raw_response"])

    def test_http_error_is_not_counted_as_valid_response(self):
        counts = parser_counts([{"calls": [{"stage": "action", "error": "timeout"}]}])
        self.assertEqual(counts["action"]["no_text"], 1)
        self.assertIsNone(counts["action"]["strict_success_rate"])

    def test_legacy_counts_use_selected_parser(self):
        call = dict(stage="action", raw_response="legacy text", parsers={
            "strict": {"status": "rejected"}, "legacy": {"status": "parsed"}})
        counts = parser_counts([{"calls": [call]}], "legacy")["action"]
        self.assertEqual(counts["selected_parsed"], 1)
        self.assertEqual(counts["strict_parsed"], 0)

    def test_cloud_sdk_is_loaded_only_when_legacy_client_is_called(self):
        from llm_controller.cloud_client import OpenAI
        from types import SimpleNamespace
        fake_client = object()
        with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=lambda **kwargs: fake_client)}):
            self.assertIs(OpenAI(api_key="test"), fake_client)

    def test_fixture_cannot_advance_production_loop(self):
        flow, _ = self.setup_flow()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.execute(folder, flow, FixtureReplies("strict"))
        self.assertEqual(flow.env.steps, 0)

    def test_deadline_blocks_request(self):
        class Inner:
            timeout = 120
            last_response = "stale"
            def complete(self, *args):
                raise AssertionError("Must not call expired transport")
        transport = BudgetTransport(Inner(), 1)
        transport.deadline = -1
        with self.assertRaises(TimeoutError):
            transport.complete([], "action", {})
        self.assertIsNone(transport.last_response)

    def test_entry_import_is_free_of_cloud_simulator_and_execution(self):
        original = builtins.__import__
        def guard(name, *args, **kwargs):
            if name.startswith(("gym", "highway_env", "openai", "langchain", "chromadb")):
                raise AssertionError("Unexpected import: "+name)
            return original(name, *args, **kwargs)
        spec = importlib.util.spec_from_file_location("project_entry", ROOT/"Run_multi_CAV_LLM.py")
        module = importlib.util.module_from_spec(spec)
        with patch("builtins.__import__", side_effect=guard):
            spec.loader.exec_module(module)
            with patch("llm_controller.qwen_episode.main", return_value=0) as run:
                self.assertEqual(module.main(["--backend", "qwen", "--output-dir", "unused"]), 0)
                self.assertEqual(run.call_args.args[0].max_steps, 1)

    def test_wrapper_targets_actual_main_file(self):
        command = traffic_args(Path("out"), "strict", 0, project_entry=True, max_steps=3)
        self.assertTrue(command[2].endswith("Run_multi_CAV_LLM.py"))
        self.assertEqual(command[command.index("--max-steps")+1], "3")
        self.assertNotIn("--apply-step", command)
        with self.assertRaises(ValueError):
            traffic_args(Path("out"), "strict", 0, project_entry=True, apply_step=True)

    def test_changed_python_files_accept_python38_grammar(self):
        for name in ("Run_multi_CAV_LLM.py", "llm_controller/qwen_episode.py",
                     "llm_controller/cloud_client.py", "llm_controller/qwen_step.py",
                     "validation/run_qwen_live_session.py"):
            ast.parse((ROOT/name).read_text(encoding="utf-8"), feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
