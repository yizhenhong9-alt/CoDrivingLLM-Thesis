"""M21-R3 frozen prompt configuration and live-response doubles; no model."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as lm
from llm_controller.memory_prompt import QUERY_SCHEMA, INTRO, MARKER, original_query, original_experience
from llm_controller.memory_replay import load_config, run_replay, validate_result
from llm_controller.qwen_step import MODEL
from run_qwen_live_session import traffic_args, launch_args


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.owner = patch.object(lm, 'OWNER', self.root)
        self.owner.start()
        rows = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))['rows']
        hits = [dict(id='fixture-'+str(i), text=row['would_write']['page_content'],
                     metadata=dict(row['would_write']['metadata'], source={'test_only': True}),
                     distance=0., score=1.) for i, row in enumerate(rows)]
        cases, records, counts = [], [], {}
        for i, row in enumerate(rows):
            scenario = 'prefix\n'+row['query']+'\n'
            base = 'prefix\nCurrent scenario:\n'+scenario+'\nRules:\nrules'+MARKER+'orders'
            context = dict(vehicle_id=3, available_actions=['IDLE', 'FASTER', 'SLOWER'])
            source = self.root/'step-{:04d}.json'.format(row['step_id'])
            source.write_text(lm.canonical(dict(model=MODEL, memory_mode='off', calls=[
                dict(stage='action', context=context, messages=[dict(role='system', content=base)])])), encoding='utf-8')
            ordered = hits if i == 0 else list(reversed(hits))
            prompt = base.replace(MARKER, '\n'+INTRO+original_experience(ordered)+'\n'+MARKER)
            messages = [dict(role='system', content=prompt)]
            counts[lm.text_hash(lm.canonical(messages))] = 100+i
            record = dict(source_step=str(source), source_step_sha256=lm.text_hash(source.read_text()),
                vehicle_id=3, query=original_query(scenario), query_sha256=lm.text_hash(original_query(scenario)),
                candidates=ordered, candidate_sha256=lm.text_hash(lm.canonical(ordered)),
                manifest=lm.manifest(QUERY_SCHEMA), snapshot_sha256='abc', output_tokens=256, context_limit=2048,
                candidate_count=2, injected_count=2, excluded_count=0, injected_ids=[h['id'] for h in ordered],
                base_prompt_sha256=lm.text_hash(base), final_prompt_sha256=lm.text_hash(prompt),
                messages=messages, input_tokens=100+i)
            records.append(record)
            cases.append(dict(scenario=scenario, base_prompt=base, hits=ordered, source_step=str(source),
                              source_step_sha256=record['source_step_sha256'], vehicle_id=3))
        self.accepted = dict(status='PASS', manifest=lm.manifest(QUERY_SCHEMA), records=records,
                             snapshot_sha256='abc', oversize_minilm_rejected_without_write=True)
        self.counts = dict(status='PASS', counts=counts, cases_sha256=lm.text_hash(lm.canonical(cases)+'\n'))
        self.config = dict(format='m21-r3-frozen-retrieval-v1', model=MODEL,
                           context_limit=2048, output_tokens=256, artifacts={})
        self.config_path = self.root/'config.json'
        self.publish()
    def publish(self):
        for name, value in (('acceptance', lm.canonical(self.accepted)),
                            ('counts', lm.canonical(self.counts)),
                            ('commit', 'd3626020622939f6e3074bf131e2dbb6d309002c\n')):
            path = self.root/(name+'.txt')
            path.write_bytes(value.encode('utf-8'))
            self.config['artifacts'][name] = dict(path=str(path), sha256=lm.text_hash(value))
        self.config_path.write_text(lm.canonical(self.config), encoding='utf-8')
    def tearDown(self):
        self.owner.stop()
        self.temp.cleanup()
    def transport(self, wrong=False):
        class Fake:
            mode, max_tokens, last_response = 'live', 256, None
            def __init__(self):
                self.calls = []
            def complete(self, messages, stage, context):
                self.calls.append((messages, stage, context))
                raw = json.dumps(dict(vehicle_id=99 if wrong else 3, decision='IDLE'))
                self.last_response = dict(test_only=True, content=raw)
                return raw
        return Fake()
    def test_bundle_two_exact_requests_strict_actions_zero_steps(self):
        bundle = load_config(self.config_path)
        report, saved = {}, []
        transport = self.transport()
        run_replay(bundle, transport, report, lambda r: saved.append(copy.deepcopy(r)))
        validate_result(report)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(report['actual_environment_steps'], 0)
        self.assertEqual([c['messages'] for c in report['calls']], [r['messages'] for r in self.accepted['records']])
        self.assertTrue(all(c['api_response']['test_only'] for c in report['calls']))
        self.assertTrue(any(r.get('status') == 'running' for r in saved))
    def test_bad_response_preserved_stops_no_retry(self):
        report, transport = {}, self.transport(wrong=True)
        with self.assertRaises(ValueError):
            run_replay(load_config(self.config_path), transport, report, lambda r: None)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('99', report['calls'][0]['raw_response'])
        self.assertIsNotNone(report['calls'][0]['api_response'])
    def test_hash_or_manifest_changed_rejected(self):
        (self.root/'acceptance.txt').write_text('{}')
        with self.assertRaises(ValueError):
            load_config(self.config_path)
        self.accepted['manifest'] = lm.manifest('wrong')
        self.publish()
        with self.assertRaises(ValueError):
            load_config(self.config_path)
    def test_token_count_changed_rejected(self):
        self.accepted['records'][0]['input_tokens'] = 9000
        self.publish()
        with self.assertRaises(ValueError):
            load_config(self.config_path)
    def test_source_changed_rejected(self):
        source = Path(self.accepted['records'][0]['source_step'])
        source.write_text('{}')
        with self.assertRaises(ValueError):
            load_config(self.config_path)
    def test_transport_timeout_stops_without_second_request(self):
        transport, report = self.transport(), {}
        from unittest.mock import Mock
        transport.complete = Mock(side_effect=TimeoutError('test timeout'))
        with self.assertRaises(TimeoutError):
            run_replay(load_config(self.config_path), transport, report, lambda r: None)
        self.assertEqual(transport.complete.call_count, 1)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['qwen_calls'], 1)
    def test_result_cannot_claim_steps_or_missing_parsing(self):
        for report in (dict(status='memory_responses_validated', actual_environment_steps=1,
                            qwen_calls=2, calls=[{'parsed_action': {}}, {'parsed_action': {}}]),
                       dict(status='memory_responses_validated', actual_environment_steps=0,
                            qwen_calls=2, calls=[{}, {}])):
            with self.assertRaises(ValueError):
                validate_result(report)
    def test_artifact_path_escape_rejected(self):
        self.config['artifacts']['acceptance']['path'] = str(self.root.parent/'outside.txt')
        self.config_path.write_text(lm.canonical(self.config), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_config(self.config_path)
    def test_replay_command_strict_no_step_only(self):
        args = traffic_args(self.root, 'strict', 0, memory_replay_config=self.config_path)
        self.assertIn(str(ROOT/'validation/run_memory_prompt_replay.py'), args)
        self.assertNotIn('--apply-step', args)
        for kwargs in (dict(apply_step=True), dict(project_entry=True)):
            with self.assertRaises(ValueError):
                traffic_args(self.root, 'strict', 0, memory_replay_config=self.config_path, **kwargs)
        with self.assertRaises(ValueError):
            traffic_args(self.root, 'legacy', 0, memory_replay_config=self.config_path)
        self.assertEqual(launch_args()[launch_args().index('--max-model-len')+1], '2048')
    def test_python38_and_no_ml(self):
        for file in ('llm_controller/memory_replay.py', 'validation/run_memory_prompt_replay.py',
                     'validation/prepare_memory_replay.py'):
            ast.parse((ROOT/file).read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'transformers', 'gym')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
