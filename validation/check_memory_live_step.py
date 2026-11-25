"""Offline checks of the M22-R2 acceptance gate; no model or simulator imports."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.accept_memory_live_step import validate_live_step
from llm_controller.local_memory import canonical, text_hash


def sample():
    outer = dict(status='project_step_limit_reached', traffic_exit_code=0,
                 shutdown=dict(exit_code=0, clean_observation=True, port_closed=True,
                               remaining_known_processes=[], warnings=[]))
    session = dict(opened=True, closed=True, final_snapshot_verified=True, initial_count=0,
                   final_count=4, writes=4, queries=4, initial_snapshot_sha256='s0', final_snapshot_sha256='s4')
    episode = dict(memory_mode='on', entry_point='Run_multi_CAV_LLM.py', seed=0,
                   actual_environment_steps=1, memory_module_imported=False, step_files=['step-0000.json'],
                   memory_session=session)
    call = dict(sent_to_model=True, parsers={'strict': dict(status='parsed', value=dict(action_id=1))},
                token_budget=dict(input_tokens=100))
    step = dict(status='single_step_complete', actual_environment_steps=1, calls=[deepcopy(call) for _ in range(5)],
                memory_queries=[], memory_updates=[])
    for i in range(4):
        meta = dict(human_question='None', negotiation_result='None', final_action='[1]',
                    source=dict(test_only=True, method='original-per-vehicle-pre-step'))
        event = dict(id=str(i), text='example', metadata=meta, status='verified', count_before=i,
                     count_after=i+1, snapshot_before='s'+str(i), snapshot_after='s'+str(i+1),
                     write_receipt=dict(id=str(i), text_sha256=text_hash('example'), metadata_sha256=text_hash(canonical(meta))))
        step['memory_queries'].append(dict(snapshot_sha256='s'+str(i), corpus_count=i, candidate_count=min(i, 2),
            candidates=[dict(id=e['id'], text=e['text'], metadata=e['metadata']) for e in step['memory_updates'][:2]]))
        step['memory_updates'].append(event)
    return outer, episode, step


class Tests(unittest.TestCase):
    def test_valid_receipts(self):
        validate_live_step(*sample())

    def test_reject_scope_or_fixture_or_corrupt_write(self):
        for kind in ('zero', 'fixture', 'hash', 'candidate', 'shutdown', 'count'):
            with self.subTest(kind=kind):
                outer, episode, step = sample()
                if kind == 'zero': episode['actual_environment_steps'] = 0
                if kind == 'fixture': step['calls'][0]['sent_to_model'] = False
                if kind == 'hash': step['memory_updates'][0]['write_receipt']['text_sha256'] = 'bad'
                if kind == 'candidate': step['memory_queries'][1]['candidates'][0]['id'] = 'unknown'
                if kind == 'shutdown': outer['shutdown']['port_closed'] = False
                if kind == 'count': step['memory_queries'][2]['corpus_count'] = 1
                with self.assertRaises(ValueError): validate_live_step(outer, episode, step)

    def test_python38_syntax(self):
        for name in ('accept_memory_live_step.py', 'check_memory_live_step.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'), feature_version=(3, 8))


if __name__ == '__main__':
    unittest.main()
