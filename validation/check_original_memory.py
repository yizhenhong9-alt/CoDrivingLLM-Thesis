"""M22 original per-vehicle update tests using HTTP/Chroma/encoder doubles."""
import ast
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import HTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as lm
from llm_controller.chroma_memory import ChromaMemoryStore
from llm_controller.original_memory import OriginalMemorySession, original_payload
from llm_controller.memory_http import MemoryServiceError
from llm_controller.memory_prompt import QUERY_SCHEMA
from llm_controller.qwen_step import run_step
from llm_controller.qwen_transport import FixtureReplies
from validation.serve_local_memory import make_handler
from validation.check_chroma_memory import FakeClient
from validation.check_local_memory import unit
import check_qwen_single_step as step_checks


def attach_original_update(agent):
    tree = ast.parse((ROOT/'llm_controller/llm_agent_action.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'memory_update')
    tree = ast.parse((ROOT/'llm_controller/prompt_llm.py').read_text(encoding='utf-8'))
    comment = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate_comment')
    scope = {'re': re}
    exec(compile(ast.Module(body=[comment, method], type_ignores=[]), '<preserved-original-methods>', 'exec'), scope)
    agent.memory_update = scope['memory_update'].__get__(agent)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.owner = patch.object(lm, 'OWNER', self.root)
        self.owner.start()
        self.spec = lm.manifest(QUERY_SCHEMA)
        fake = FakeClient()
        self.store = ChromaMemoryStore(self.root/'db', self.spec, create=True,
                                      _client_factory=lambda path: fake)
        class Encoder:
            manifest = self.spec
            def encode(self, texts):
                return [unit() for text in texts]
        self.memory = lm.LocalMemory(self.store, Encoder())
        self.server = HTTPServer(('127.0.0.1', 0), make_handler(self.spec, self.memory, lambda messages: 100))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = dict(format='m22-original-v1', manifest=self.spec, port=self.server.server_port,
            timeout=30, store_path_sha256=lm.text_hash(self.store.path.as_posix()),
            context_limit=2048, output_tokens=256, test_only=True)
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.owner.stop()
        self.temp.cleanup()
    def flow(self):
        flow = step_checks.FlowTests()
        flow.setUp()
        attach_original_update(flow.action)
        flow.action.prompt_engineer = lambda *args: 'prefix\n\n Conflict info is empty\n'
        return flow
    def run_flow(self, session, episode='episode-1', apply=False, live=False):
        flow = self.flow()
        transport = FixtureReplies('strict')
        if live:
            transport.mode, transport.last_response = 'live', {'test_only': True}
        report = {}
        if apply:
            def step(actions, env):
                self.assertEqual(self.store.count(), 2)
                self.assertTrue(all(row['status'] == 'verified' for row in report['memory_updates']))
                flow.steps.append(actions)
                return None, 0, False, {}
            flow.env.step = step
        run_step(flow.env, flow.negotiation, flow.action, transport, report, parser_mode='strict',
                 episode_id=episode, apply_step=apply, memory_prompt=session)
        return flow, report
    def test_empty_then_same_step_visibility_and_shared_next_episode(self):
        with OriginalMemorySession(self.config) as session:
            flow, report = self.run_flow(session)
            self.assertEqual([r['corpus_count'] for r in report['memory_queries']], [0, 1])
            self.assertEqual([r['candidate_count'] for r in report['memory_queries']], [0, 1])
            self.assertEqual(report['memory_queries'][1]['candidates'][0]['id'], report['memory_updates'][0]['id'])
            self.assertEqual(flow.steps, [])
            self.assertEqual(session.receipt['writes'], 2)
        with OriginalMemorySession(self.config) as session:
            _, report = self.run_flow(session, 'episode-2')
            self.assertEqual(session.receipt['initial_count'], 2)
            self.assertEqual([r['corpus_count'] for r in report['memory_queries']], [2, 3])
            self.assertEqual(session.receipt['final_count'], 4)
    def test_original_metadata_and_heuristic_preserved(self):
        with OriginalMemorySession(self.config) as session:
            _, report = self.run_flow(session)
        for event in report['memory_updates']:
            self.assertEqual(event['text'], ' Conflict info is empty')
            self.assertEqual({k: event['metadata'][k] for k in ('human_question','negotiation_result','final_action','comments')},
                dict(human_question='None', negotiation_result='None', final_action='[1]', comments='recommended to FASTER'))
            self.assertTrue(event['metadata']['source']['test_only'])
            self.assertEqual(event['status'], 'verified')
    def test_all_writes_before_env_step(self):
        with OriginalMemorySession(self.config) as session:
            flow, report = self.run_flow(session, apply=True, live=True)
        self.assertEqual(len(flow.steps), 1)
        self.assertEqual(report['environment_steps'], 1)
    def test_later_invalid_reply_keeps_prior_write_no_step(self):
        flow = self.flow()
        transport = FixtureReplies('strict')
        original = transport.complete
        transport.complete = lambda messages, stage, context: ('{"vehicle_id":999,"decision":"IDLE"}'
            if stage == 'action' and context['vehicle_id'] == 4 else original(messages, stage, context))
        report = {}
        with OriginalMemorySession(self.config) as session:
            with self.assertRaises(ValueError):
                run_step(flow.env, flow.negotiation, flow.action, transport, report,
                         parser_mode='strict', episode_id='bad-later', memory_prompt=session)
            self.assertEqual(session.receipt['writes'], 1)
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(flow.steps, [])
    def test_write_failure_not_success_or_retried(self):
        flow, report = self.flow(), {}
        with OriginalMemorySession(self.config) as session:
            with patch.object(session.client, 'add', side_effect=TimeoutError('test timeout')) as add:
                with self.assertRaises(TimeoutError):
                    run_step(flow.env, flow.negotiation, flow.action, FixtureReplies('strict'), report,
                             parser_mode='strict', episode_id='timeout', memory_prompt=session)
                self.assertEqual(add.call_count, 1)
        self.assertEqual(report['memory_updates'][0]['status'], 'failed-outcome-unknown-do-not-retry')
        self.assertEqual(self.store.count(), 0)
    def test_fixture_cannot_write_production_store(self):
        config = dict(self.config, test_only=False)
        with OriginalMemorySession(config) as session:
            with self.assertRaises(ValueError):
                self.run_flow(session)
        self.assertEqual(self.store.count(), 0)
    def test_bad_relation_rejects_before_write(self):
        agent = self.flow().action
        with self.assertRaises(IndexError):
            original_payload(agent, 'prefix\nnot a relation', 1)
        self.assertEqual(self.store.count(), 0)
    def test_payload_matches_original_r2(self):
        rows = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))['rows']
        agent = self.flow().action
        for row in rows:
            payload = original_payload(agent, 'prefix\n'+row['query']+'\n', row['action_id'])
            self.assertEqual(payload['text'], row['would_write']['page_content'])
            self.assertEqual(payload['metadata'], row['would_write']['metadata'])
    def test_episode_uses_one_session_across_steps(self):
        from llm_controller.qwen_episode import run_episode
        flow = self.flow()
        flow.env.steps = 0
        def step(actions, env):
            self.assertEqual(self.store.count(), 2*(env.steps+1))
            env.steps += 1
            return None, 0, False, {}
        flow.env.step = step
        live = FixtureReplies('strict')
        live.mode, live.last_response = 'live', {'test_only': True}
        folder = self.root/'episode-output'
        folder.mkdir()
        with OriginalMemorySession(self.config) as session:
            summary = dict(git_commit='test-commit')
            run_episode(flow.env, lambda env: flow.negotiation, lambda env: flow.action,
                live, folder, parser_mode='strict', episode_id='two-steps', max_steps=2,
                persist_summary=lambda value: None, summary=summary, snapshot=lambda env: [], memory_prompt=session)
            self.assertEqual(session.receipt['queries'], 4)
            self.assertEqual(session.receipt['writes'], 4)
        self.assertEqual(summary['status'], 'step_limit_reached')
        for index, expected in enumerate(([0,1], [2,3])):
            report = json.loads((folder/'step-{:04d}.json'.format(index)).read_text())
            self.assertEqual([q['corpus_count'] for q in report['memory_queries']], expected)
    def test_four_vehicle_acceptance_validator_and_two_scopes(self):
        from types import SimpleNamespace
        from validation.accept_original_memory import validate_original_capture
        for index in (0, 1):
            flow = self.flow()
            flow.cars = [step_checks.Vehicle(number) for number in (3,4,5,6)]
            flow.env.road.vehicles = flow.env.controlled_vehicles = flow.cars
            flow.env.action_type.agents_action_types = [SimpleNamespace(controlled_vehicle=v,
                actions={1:'IDLE',3:'FASTER',4:'SLOWER'}) for v in flow.cars]
            flow.negotiation.detect_conflicts = lambda env: {v:{} for v in flow.cars}
            report = {}
            with OriginalMemorySession(self.config) as session:
                run_step(flow.env, flow.negotiation, flow.action, FixtureReplies('strict'), report,
                         parser_mode='strict', episode_id='four-scope-'+str(index), memory_prompt=session)
            report.update(actual_environment_steps=0, memory_module_imported=False, memory_session=session.receipt)
            validate_original_capture(report, 4*index)
        self.assertEqual(self.store.count(), 8)
    def test_duplicate_id_fails_without_overwriting(self):
        with OriginalMemorySession(self.config) as session:
            self.run_flow(session, 'same-episode')
        with OriginalMemorySession(self.config) as session:
            with self.assertRaises(MemoryServiceError):
                self.run_flow(session, 'same-episode')
        self.assertEqual(self.store.count(), 2)
    def test_cli_only_off_on_and_no_write_switch(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('entry_m22', ROOT/'Run_multi_CAV_LLM.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch('llm_controller.qwen_episode.main', return_value=0) as run:
            entry.main(['--backend','qwen','--output-dir','unused','--memory','on','--memory-config','config.json'])
            self.assertEqual(run.call_args.args[0].memory, 'on')
            entry.main(['--backend','qwen','--output-dir','unused'])
            self.assertEqual(run.call_args.args[0].memory, 'off')
        for flags in (['--memory','on'], ['--memory','off','--memory-config','config.json'], ['--memory-write','off']):
            with self.assertRaises(SystemExit):
                entry.main(['--backend','qwen','--output-dir','unused']+flags)
    def test_python38_no_ml(self):
        ast.parse((ROOT/'llm_controller/original_memory.py').read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch','transformers','chromadb','gym')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
