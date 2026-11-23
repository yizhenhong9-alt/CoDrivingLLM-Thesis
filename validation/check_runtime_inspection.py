"""M09 collector helper tests; no actual system commands or model imports."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from inspect_qwen_runtime import memory_values, source_excerpt, command_snapshot


class RuntimeInspectionTests(unittest.TestCase):
    def test_memory_snapshot_uses_current_available(self):
        result = memory_values("MemTotal: 1000 kB\nMemAvailable: 300 kB\nSwapFree: 20 kB\nCached: 400 kB")
        self.assertEqual(result["MemAvailable_bytes"], 300*1024)
        self.assertNotIn("Cached_bytes", result)

    def test_source_excerpt_keeps_line_numbers_without_executing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.py"
            path.write_text("raise RuntimeError('must not run')\n# SIGTERM\n# rest\n", encoding="utf-8")
            result = source_excerpt(path, radius=0)
            self.assertEqual(result["lines"], [{"line": 2, "text": "# SIGTERM"}])
            self.assertEqual(len(result["sha256"]), 64)

    def test_missing_command_is_recorded(self):
        with patch("inspect_qwen_runtime.subprocess.run", side_effect=FileNotFoundError("missing")):
            self.assertIn("error", command_snapshot(["nvidia-smi"]))

    def test_no_model_modules_loaded(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
