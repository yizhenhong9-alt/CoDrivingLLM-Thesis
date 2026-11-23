"""M04 offline checks: execute actual entry assignment and action prompt builder.

Cloud and simulator dependencies are replaced by explicit test doubles. These
tests are not a complete simulator run or a real API test.
"""
import ast
import builtins
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.memory_mode import create_memory


class MemoryOffTests(unittest.TestCase):
    def test_original_assignment_constructed_memory_each_time(self):
        # Baseline statement from HEAD, preserved verbatim in the report.
        calls = []
        scope = {"env": object(), "DrivingMemory": lambda env: calls.append(env)}
        for _ in range(3):
            exec("memory = DrivingMemory(env)", scope)
        self.assertEqual(len(calls), 3)

    def test_actual_entry_off_assignment_has_zero_dependency_calls(self):
        tree = ast.parse((ROOT / "Run_multi_CAV_LLM.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and
                             node.module == "llm_controller.memory" for node in ast.walk(tree)))
        config = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "MEMORY_MODE" for t in node.targets))
        assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "memory" for t in node.targets))
        calls = []
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "llm_controller.memory" or name.startswith(("langchain", "chromadb")):
                calls.append(name)
                raise AssertionError("Memory dependency imported in off mode")
            return original_import(name, *args, **kwargs)

        scope = {"env": object(), "create_memory": create_memory}
        code = compile(ast.Module(body=[config, assignment], type_ignores=[]), "<actual-entry>", "exec")
        with patch("builtins.__import__", side_effect=guarded_import):
            for _ in range(3):
                exec(code, scope)
                self.assertIsNone(scope["memory"])
        self.assertEqual(calls, [])
        self.assertNotIn("llm_controller.memory", sys.modules)

    def test_memory_on_fails_before_cloud_fallback(self):
        with self.assertRaises(NotImplementedError):
            create_memory(object(), "on")

    def test_unknown_mode_is_not_silently_off(self):
        with self.assertRaises(ValueError):
            create_memory(object(), "OFF")

    def test_actual_action_builder_does_not_touch_memory(self):
        tree = ast.parse((ROOT / "llm_controller/llm_agent_action.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "LlmAgent_action_module")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "send_to_chatgpt")
        prompt = SimpleNamespace(SYSTEM_MESSAGE_PREFIX_intersection="intersection",
                                 get_traffic_rules=lambda flag: "rules",
                                 get_decision_cautions=lambda flag: "cautions")
        fake_completion = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='"decision": {"IDLE"}'))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: fake_completion)))
        fake_httpx = SimpleNamespace(Client=lambda **kwargs: object())
        memory_calls = []

        class ForbiddenMemory:
            def __getattr__(self, name):
                memory_calls.append(name)
                raise AssertionError("Unexpected memory operation: " + name)

        agent = SimpleNamespace(is_intersection=True, pre_prompt=prompt,
                                extract_decision=lambda text: "IDLE",
                                get_action_id_from_name=lambda name, mapping: 1,
                                ACTIONS_ALL={1: "IDLE"})
        scope = {"OpenAI": lambda **kwargs: client, "api_key": "offline-test",
                 "np": SimpleNamespace(array=lambda value: value)}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "<actual-action>", "exec"), scope)
        with patch.dict(sys.modules, {"httpx": fake_httpx}):
            result = scope[method.name](agent, object(), "scenario", "orders", ForbiddenMemory())
        self.assertEqual(result, [1])
        self.assertEqual(memory_calls, [])


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
