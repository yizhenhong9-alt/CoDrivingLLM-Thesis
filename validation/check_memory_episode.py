"""Offline terminal-vs-limit and rolling corpus gate regression checks."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.check_memory_live_step import sample
from validation.accept_memory_episode import validate_episode
from llm_controller.local_memory import canonical, text_hash


def terminal_sample():
    outer, episode, step = sample()
    outer['status'] = 'project_episode_terminal'
    episode['status'] = 'episode_terminal'
    step.update(step_id=0, mode='live', done=True)
    for event in step['memory_updates']:
        event['metadata']['source']['step_id'] = 0
        event['write_receipt']['metadata_sha256'] = text_hash(canonical(event['metadata']))
    return outer, episode, [step]


class Tests(unittest.TestCase):
    def test_terminal_gate(self):
        validate_episode(*terminal_sample())

    def test_reject_limit_or_bad_cross_step_state(self):
        for kind in ('limit', 'not_done', 'snapshot', 'count', 'fixture'):
            with self.subTest(kind=kind):
                outer, episode, steps = terminal_sample()
                if kind == 'limit': episode['status'] = 'step_limit_reached'
                if kind == 'not_done': steps[0]['done'] = False
                if kind == 'snapshot': steps[0]['memory_queries'][0]['snapshot_sha256'] = 'bad'
                if kind == 'count': episode['memory_session']['final_count'] = 3
                if kind == 'fixture': steps[0]['mode'] = 'fixture'
                with self.assertRaises(ValueError): validate_episode(outer, episode, steps)

    def test_python38_syntax(self):
        for name in ('accept_memory_episode.py', 'accept_memory_live_step.py', 'check_memory_episode.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'), feature_version=(3, 8))


if __name__ == '__main__':
    unittest.main()
