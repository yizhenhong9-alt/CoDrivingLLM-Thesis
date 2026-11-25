"""M21-R4 real loopback count/retrieval with stdlib doubles only."""
from contextlib import ExitStack
import ast
import copy
from pathlib import Path
import sys
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import manifest
from llm_controller.memory_http import MemoryHTTPClient, QWEN_TOKENIZER, MemoryServiceError
from llm_controller.memory_prompt import QUERY_SCHEMA
from llm_controller.memory_session import OnlineMemorySession
from llm_controller.qwen_step import run_step
from llm_controller.qwen_transport import FixtureReplies
from validation.serve_local_memory import make_handler
from validation.check_memory_http import Memory
from run_qwen_single_step import allow_memory_only
import check_qwen_single_step as step_checks


class Tests(unittest.TestCase):
    def setUp(self):
        self.expected = manifest(QUERY_SCHEMA)
        self.memory = Memory(self.expected)
        self.memory.store.writable = False
        self.server = HTTPServer(('127.0.0.1', 0), make_handler(self.expected, self.memory, lambda messages: 100))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = MemoryHTTPClient(self.expected, self.server.server_port)
        self.config = dict(format='m21-r4-readonly-v1', manifest=self.expected, port=self.server.server_port,
                           timeout=30, snapshot_sha256=self.memory.store.snapshot_sha256(), context_limit=2048, output_tokens=256)
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def test_count_hash_and_identity(self):
        self.assertEqual(self.client.count_messages([dict(role='system', content='full prompt')]), 100)
        self.assertEqual(self.client.status()['tokenizer'], QWEN_TOKENIZER)
        with patch.object(self.client, '_call', return_value=dict(tokenizer=QWEN_TOKENIZER, messages_sha256='wrong', input_tokens=100)):
            with self.assertRaises(ValueError):
                self.client.count_messages([dict(role='system', content='full prompt')])
    def test_disabled_counter_and_bad_messages_stop(self):
        self.server.RequestHandlerClass = make_handler(self.expected, self.memory)
        with self.assertRaises(MemoryServiceError):
            self.client.count_messages([dict(role='system', content='full prompt')])
        for messages in ([], [dict(role='user', content='x')], [dict(role='system', content='')]):
            with self.assertRaises(ValueError):
                self.client.count_messages(messages)
    def test_scope_open_query_all_requests_close(self):
        session = OnlineMemorySession(self.config)
        with session:
            flow = step_checks.FlowTests()
            flow.setUp()
            report = {}
            run_step(flow.env, flow.negotiation, flow.action, FixtureReplies('strict'), report,
                     parser_mode='strict', episode_id='scope-test', memory_prompt=session)
            self.assertEqual(report['memory_mode'], 'retrieve-only')
            self.assertEqual(len(report['memory_queries']), 2)
            self.assertTrue(all(call['token_budget']['input_tokens'] == 100 for call in report['calls']))
            self.assertEqual(flow.steps, [])
        self.assertTrue(session.receipt['closed'])
        self.assertTrue(session.receipt['final_snapshot_verified'])
        with self.assertRaises(ValueError):
            session.count_messages([dict(role='system', content='after close')])
        with self.assertRaises(ValueError):
            session.__enter__()
    def test_writable_or_corpus_change_rejected_and_closed(self):
        session = OnlineMemorySession(self.config)
        self.memory.store.writable = True
        with self.assertRaises(ValueError):
            session.__enter__()
        self.assertTrue(session.receipt['closed'])
        self.memory.store.writable = False
        session = OnlineMemorySession(self.config)
        with self.assertRaises(ValueError):
            with session:
                self.memory.store.rows['changed'] = dict(test=True)
        self.assertTrue(session.receipt['closed'])
    def test_original_error_preserved_and_client_closed(self):
        session = OnlineMemorySession(self.config)
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            with session:
                self.memory.store.rows['changed'] = dict(test=True)
                raise RuntimeError('original failure')
        self.assertTrue(session.receipt['closed'])
        self.assertIn('final_snapshot_error', session.receipt)
    def test_only_memory_port_allowed_in_fixture(self):
        import socket
        with ExitStack() as stack:
            allow_memory_only(stack, self.server.server_port)
            self.assertEqual(self.client.count_messages([dict(role='system', content='allowed')]), 100)
            for address in (('example.com', 443), ('127.0.0.1', 18080), ('::1', self.server.server_port)):
                with self.assertRaises(RuntimeError):
                    socket.create_connection(address, timeout=.1)
    def test_large_request_and_step_rejected_before_submission(self):
        with self.assertRaises(ValueError):
            self.client.count_messages([dict(role='system', content='x'*1048576)])
        session = OnlineMemorySession(self.config)
        with session:
            flow = step_checks.FlowTests()
            flow.setUp()
            live = FixtureReplies('strict')
            live.mode = 'live'
            with self.assertRaises(ValueError):
                run_step(flow.env, flow.negotiation, flow.action, live, {}, parser_mode='strict',
                         episode_id='no-step', apply_step=True, memory_prompt=session)
            self.assertEqual(flow.steps, [])
    def test_token_overflow_stops_negotiation(self):
        self.server.RequestHandlerClass = make_handler(self.expected, self.memory, lambda messages: 2048)
        session = OnlineMemorySession(self.config)
        with session:
            flow = step_checks.FlowTests()
            flow.setUp()
            transport = FixtureReplies('strict')
            with patch.object(transport, 'complete') as complete:
                with self.assertRaises(ValueError):
                    run_step(flow.env, flow.negotiation, flow.action, transport, {}, parser_mode='strict',
                             episode_id='overflow', memory_prompt=session)
                complete.assert_not_called()
    def test_python38_no_ml(self):
        for file in ('llm_controller/memory_session.py', 'validation/accept_online_memory.py'):
            ast.parse((ROOT/file).read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'transformers', 'chromadb', 'gym')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
