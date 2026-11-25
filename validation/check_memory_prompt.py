"""M21-R1 stdlib reference semantics / prompt / orchestration tests."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import manifest
from llm_controller.memory_prompt import (original_query, original_experience, fit_prompt,
                                          RetrievalPrompt, QUERY_SCHEMA, MARKER, INTRO)
from llm_controller.qwen_step import run_step
from llm_controller.qwen_transport import FixtureReplies
import check_qwen_single_step as step_checks


class Tests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))['rows']
        self.hits = [dict(id='fixture-'+str(i), text=row['would_write']['page_content'],
                          metadata=dict(row['would_write']['metadata'], source={'test_only': True}),
                          distance=0., score=1.) for i, row in enumerate(self.rows)]
        self.base = 'prefix\nRules:\noriginal rules'+MARKER+'orders\nstrict output'
    def test_original_query_and_format_exact(self):
        for row, hit in zip(self.rows, self.hits):
            self.assertEqual(original_query('prefix\n'+row['query']+'\n\n'), row['query'])
            self.assertEqual(original_experience([hit]), row['format_only_if_selected_as_hit'])
    def test_empty_still_original_ending_and_zero_recorded(self):
        prompt, receipt = fit_prompt(self.base, [], lambda messages: 100,
                                    output_tokens=256, context_limit=2048)
        self.assertIn(original_experience([]), prompt)
        self.assertEqual(receipt['candidate_count'], 0)
        self.assertEqual(receipt['injected_count'], 0)
    def test_budget_drops_whole_last_candidate_only(self):
        def counter(messages):
            return 100+100*messages[0]['content'].count('- Last time ')
        prompt, receipt = fit_prompt(self.base, self.hits, counter, output_tokens=50, context_limit=250)
        self.assertEqual(receipt['injected_count'], 1)
        self.assertIn('[4]', prompt)
        self.assertNotIn('[3]', prompt)
        self.assertEqual(prompt.replace('\n'+INTRO+original_experience(self.hits[:1])+'\n', '', 1), self.base)
    def test_oversize_and_invalid_counter_fail(self):
        for count in (lambda messages: 3000, lambda messages: True):
            with self.assertRaises(ValueError):
                fit_prompt(self.base, self.hits, count, output_tokens=256, context_limit=2048)
    def test_readonly_manifest_snapshot_and_errors(self):
        client = Mock(manifest=manifest(QUERY_SCHEMA))
        client.status.return_value = dict(writable=False, snapshot_sha256='abc')
        client.retrieve.return_value = self.hits
        view = RetrievalPrompt(client, lambda messages: 100)
        prompt, receipt = view.prepare('prefix\n\n Conflict info is empty\n', self.base)
        client.retrieve.assert_called_once_with('\n Conflict info is empty', top_k=2)
        self.assertEqual(receipt['injected_ids'], ['fixture-0', 'fixture-1'])
        client.add.assert_not_called()
        client.status.return_value = dict(writable=True, snapshot_sha256='abc')
        with self.assertRaises(ValueError):
            view.prepare('text', self.base)
        client.status.side_effect = [dict(writable=False, snapshot_sha256='a'),
                                     dict(writable=False, snapshot_sha256='b')]
        with self.assertRaises(ValueError):
            view.prepare('text', self.base)
        with self.assertRaises(ValueError):
            RetrievalPrompt(Mock(manifest=manifest('r7-test')), lambda messages: 1)
    def test_fixture_orchestration_negotiation_unchanged_no_step_or_write(self):
        flow = step_checks.FlowTests()
        flow.setUp()
        baseline = {}
        run_step(flow.env, flow.negotiation, flow.action, FixtureReplies('strict'), baseline,
                 parser_mode='strict', episode_id='test')
        # The original flow clamps speed; compare independent equivalent initial state.
        for car in flow.cars:
            car.speed = 7
        client = Mock(manifest=manifest(QUERY_SCHEMA))
        client.status.return_value = dict(writable=False, snapshot_sha256='abc')
        client.retrieve.return_value = self.hits
        report = {}
        run_step(flow.env, flow.negotiation, flow.action, FixtureReplies('strict'), report,
                 parser_mode='strict', episode_id='test',
                 memory_prompt=RetrievalPrompt(client, lambda messages: 100))
        self.assertEqual(report['calls'][0]['messages'], baseline['calls'][0]['messages'])
        self.assertEqual(report['validated_actions'], baseline['validated_actions'])
        self.assertEqual(len(report['memory_queries']), 2)
        self.assertEqual(flow.steps, [])
        client.add.assert_not_called()
        live = FixtureReplies('strict')
        live.mode = 'live'
        with self.assertRaises(ValueError):
            run_step(flow.env, flow.negotiation, flow.action, live, {}, parser_mode='strict',
                     episode_id='test', memory_prompt=object())
    def test_bad_original_fields_and_boundary_rejected(self):
        with self.assertRaises(ValueError):
            original_experience([dict(metadata={})])
        with self.assertRaises(ValueError):
            fit_prompt('missing marker', self.hits, lambda messages: 100,
                       output_tokens=256, context_limit=2048)
    def test_python38_no_ml(self):
        ast.parse((ROOT/'llm_controller/memory_prompt.py').read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'chromadb', 'transformers')))

    def test_saved_prompt_replay_and_source_rejection(self):
        from validation.accept_memory_prompt import replay
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return 'chat-start'+messages[0]['content']+'chat-end'
            def encode(self, rendered, **kwargs):
                return list(range(len(rendered.split())))
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'step-0000.json'
            from llm_controller.qwen_step import MODEL
            step = dict(model=MODEL, memory_mode='off', calls=[dict(stage='action',
                context={'vehicle_id': 3}, messages=[dict(role='system',
                content='prefix\nCurrent scenario:\nprefix\n\n Conflict info is empty\nRules:\nrules'+MARKER+'orders')])])
            file.write_text(json.dumps(step), encoding='utf-8')
            result = replay(Tokenizer(), [file])
            self.assertEqual(result['action_count'], 1)
            self.assertEqual(result['records'][0]['injected_count'], 2)
            self.assertEqual(result['records'][0]['query_sha256'],
                             __import__('hashlib').sha256(b'\n Conflict info is empty').hexdigest())
            step['memory_mode'] = 'on'
            file.write_text(json.dumps(step), encoding='utf-8')
            with self.assertRaises(ValueError):
                replay(Tokenizer(), [file])


if __name__ == '__main__':
    unittest.main(verbosity=2)
