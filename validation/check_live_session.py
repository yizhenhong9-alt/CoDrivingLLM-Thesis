"""M10 helper tests with fake processes; never launch a model or send signals."""
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from run_qwen_live_session import (MODEL, launch_args, listener_inodes,
                                   parent_only_stop, traffic_args, environment, process_info)


class LiveSessionTests(unittest.TestCase):
    def test_served_name_matches_client(self):
        from llm_controller.qwen_step import MODEL as CLIENT_MODEL
        args = launch_args()
        self.assertEqual(args[args.index("--served-model-name")+1], CLIENT_MODEL)
        self.assertEqual(CLIENT_MODEL, MODEL)

    def test_original_resource_settings_preserved(self):
        args = launch_args()
        for flag, value in (("--gpu-memory-utilization", "0.40"), ("--max-model-len", "2048"),
                            ("--kv-cache-memory-bytes", "536870912"), ("--moe-backend", "triton")):
            self.assertEqual(args[args.index(flag)+1], value)
        self.assertEqual(args[args.index("--shutdown-timeout")+1], "30")

    def test_parent_signal_and_wait_only(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.return_value = 0
        result = parent_only_stop(proc)
        proc.send_signal.assert_called_once_with(signal.SIGTERM)
        proc.kill.assert_not_called()
        self.assertTrue(result["exited"])

    def test_exited_parent_receives_no_signal(self):
        proc = Mock()
        proc.poll.return_value, proc.wait.return_value = 0, 0
        parent_only_stop(proc)
        proc.send_signal.assert_not_called()

    def test_timeout_has_no_escalation(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired("fake parent", 120)
        result = parent_only_stop(proc)
        self.assertTrue(result["manual_review_required"])
        proc.kill.assert_not_called()
        self.assertEqual(proc.send_signal.call_count, 1)

    def test_live_client_never_applies_step(self):
        args = traffic_args(Path("test-run"), "strict", 0)
        self.assertEqual(args[args.index("--mode")+1], "live")
        self.assertNotIn("--apply-step", args)

    def test_listener_detection(self):
        header = "sl local_address rem_address st tx rx tr uid timeout inode\n"
        listening = "0: 0100007F:46A0 00000000:0000 0A 0 0 0 1 0 12345\n"
        connected = "1: 0100007F:46A0 00000000:0000 01 0 0 0 1 0 99999\n"
        self.assertEqual(listener_inodes(header+listening+connected), {"12345"})

    def test_process_identity_handles_spaces_and_parentheses(self):
        fields = ["S", "11", "123", "123"] + ["0"]*15 + ["456789"]
        with patch("run_qwen_live_session.Path.read_text", return_value="123 (name with ) inside) " + " ".join(fields)):
            item = process_info(123)
        self.assertEqual((item["ppid"], item["pgid"], item["start_ticks"]), (11, 123, 456789))

    def test_cache_paths_are_per_run_and_process_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.dict("os.environ", {"CUDA_VISIBLE_DEVICES": "hidden-before"}):
                env, overrides = environment(root, "GPU-test")
                self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "GPU-test")
                import os
                self.assertEqual(os.environ["CUDA_VISIBLE_DEVICES"], "hidden-before")
            for key in ("HF_HOME", "TMPDIR", "CUDA_CACHE_PATH", "VLLM_CACHE_ROOT", "TRITON_CACHE_DIR"):
                Path(overrides[key]).relative_to(root)


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
