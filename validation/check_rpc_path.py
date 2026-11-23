"""M15: reproduce the actual too-long path, without vLLM or model startup."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from run_qwen_live_session import validate_rpc_path, short_rpc_directory, environment

SHORT_TEST_ROOT = Path(__file__).resolve().parents[2]


class RpcPathTests(unittest.TestCase):
    def test_actual_m14_path_exceeds_linux_limit(self):
        path = Path("/home/nclab/Yizhen/runs/M14-project-entry/20261123T084407Z-0ea03d24/rpc")
        with self.assertRaisesRegex(ValueError, "limit 107"):
            validate_rpc_path(path)

    def test_short_spark_path_fits(self):
        path = Path("/home/nclab/Yizhen/.rpc/0123456789ab")
        self.assertLessEqual(validate_rpc_path(path), 107)

    def test_utf8_bytes_not_character_count(self):
        with self.assertRaises(ValueError):
            validate_rpc_path(Path("/"+"車"*30))

    def test_new_paths_are_exclusive_and_inside_owner(self):
        with tempfile.TemporaryDirectory(dir=SHORT_TEST_ROOT) as directory:
            owner = Path(directory).resolve()
            left, right = short_rpc_directory(owner), short_rpc_directory(owner)
            self.assertNotEqual(left, right)
            for path in (left, right):
                path.relative_to(owner)
                self.assertTrue(path.is_dir())
                self.assertLessEqual(validate_rpc_path(path), 107)

    def test_oversized_owner_rejected_before_mkdir(self):
        with patch.object(Path, "mkdir") as mkdir:
            with self.assertRaises(ValueError):
                short_rpc_directory(Path("/"+"x"*110))
            mkdir.assert_not_called()

    def test_environment_uses_short_rpc_even_with_long_run_folder(self):
        with tempfile.TemporaryDirectory(dir=SHORT_TEST_ROOT) as directory:
            owner = Path(directory).resolve()
            folder = owner / ("very-long-result-name-"*5)
            folder.mkdir()
            before = os.environ.get("VLLM_RPC_BASE_PATH")
            env, overrides = environment(folder, "fake-gpu", owner=owner)
            rpc = Path(overrides["VLLM_RPC_BASE_PATH"])
            rpc.relative_to(owner/".rpc")
            self.assertLessEqual(validate_rpc_path(rpc), 107)
            self.assertEqual(env["VLLM_RPC_BASE_PATH"], str(rpc))
            self.assertEqual(os.environ.get("VLLM_RPC_BASE_PATH"), before)


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
