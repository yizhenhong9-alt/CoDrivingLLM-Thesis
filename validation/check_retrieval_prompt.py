"""M21-R2 real loopback HTTP with Chroma/encoder/tokenizer DOUBLES only."""
import ast
import json
from pathlib import Path
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
from llm_controller.memory_http import MemoryHTTPClient, MemoryServiceError
from llm_controller.memory_prompt import RetrievalPrompt, QUERY_SCHEMA, fit_prompt, INTRO, original_experience
from validation.serve_local_memory import make_handler
from validation.check_chroma_memory import FakeClient
from validation.check_local_memory import unit
from validation.count_memory_candidates import count_candidates
from validation.accept_retrieval_prompt import make_cases, prepare_cases


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.owner = patch.object(lm, 'OWNER', self.root)
        self.owner.start()
        self.spec = lm.manifest(QUERY_SCHEMA)
        self.fake = FakeClient()
        self.store = ChromaMemoryStore(self.root/'db', self.spec, create=True,
                                      _client_factory=lambda path: self.fake)
        rows = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))['rows']
        self.rows = rows
        class Encoder:
            manifest = self.spec
            def encode(self, texts):
                return [unit(1 if 'Conflict info is empty' in text else 0) for text in texts]
        self.memory = lm.LocalMemory(self.store, Encoder())
        self.server = HTTPServer(('127.0.0.1', 0), make_handler(self.spec, self.memory))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = MemoryHTTPClient(self.spec, self.server.server_port)
        for i, row in enumerate(rows):
            self.client.add('fixture-'+str(i), row['would_write']['page_content'],
                            dict(row['would_write']['metadata'], source={'test_only': True}))
        self.store.writable = False
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.owner.stop()
        self.temp.cleanup()
    def cases(self):
        from llm_controller.qwen_step import MODEL
        from llm_controller.memory_prompt import MARKER
        for row in self.rows:
            base = 'prefix\nCurrent scenario:\nprefix\n'+row['query']+'\nRules:\nrules'+MARKER+'orders'
            step = dict(model=MODEL, memory_mode='off', calls=[dict(stage='action',
                context={'vehicle_id': row['vehicle_id']}, messages=[dict(role='system', content=base)])])
            (self.root/'step-{:04d}.json'.format(row['step_id'])).write_text(json.dumps(step), encoding='utf-8')
        return make_cases(self.root, self.client, self.rows)
    def test_http_chroma_candidates_to_count_map_to_prompt(self):
        cases = self.cases()
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return 'start '+messages[0]['content']+' end'
            def encode(self, text, **kwargs):
                return list(range(len(text.split())))
        counts = count_candidates(cases, Tokenizer())
        counter = lambda messages: counts[lm.text_hash(lm.canonical(messages))]
        before = self.store.snapshot_sha256()
        records = prepare_cases(cases, RetrievalPrompt(self.client, counter))
        self.assertEqual([r['injected_ids'][0] for r in records], ['fixture-0', 'fixture-1'])
        self.assertEqual([r['injected_count'] for r in records], [2, 2])
        self.assertEqual(self.store.snapshot_sha256(), before)
        for record in records:
            self.assertEqual(record['manifest'], self.spec)
            self.assertTrue(all(hit['metadata']['source']['test_only'] for hit in record['candidates']))
    def test_changed_candidates_or_unknown_message_hash_stop(self):
        cases = self.cases()
        cases[0]['hits'] = list(reversed(cases[0]['hits']))
        with self.assertRaises(ValueError):
            prepare_cases(cases, RetrievalPrompt(self.client, lambda messages: 100))
        with self.assertRaises(KeyError):
            prepare_cases(self.cases(), RetrievalPrompt(self.client, lambda messages: {}['missing']))
    def test_budget_zero_preserves_base_and_all_attempts(self):
        case = self.cases()[0]
        counts = lambda messages: 1800+100*messages[0]['content'].count('- Last time ')
        prompt, receipt = fit_prompt(case['base_prompt'], case['hits'], counts,
                                     output_tokens=256, context_limit=2100)
        # 2 -> 2256; 1 -> 2156; 0 -> 2056.
        self.assertEqual(receipt['injected_count'], 0)
        self.assertEqual([a['memory_count'] for a in receipt['attempts']], [2, 1, 0])
        section = '\n'+INTRO+original_experience([])+'\n'
        self.assertEqual(prompt.replace(section, '', 1), case['base_prompt'])
        with self.assertRaises(ValueError):
            fit_prompt(case['base_prompt'], case['hits'], counts, output_tokens=256, context_limit=2048)
    def test_http_and_text_limits_reject_without_writing(self):
        before = self.store.snapshot_sha256()
        self.store.writable = True
        for text, metadata in [('x'*16385, {'source': {'test_only': True}}),
                               ('text', {'source': {'large': 'x'*1048576}})]:
            with self.assertRaises(ValueError):
                self.client.add('oversize', text, metadata)
        self.assertEqual(before, self.store.snapshot_sha256())
    def test_encoder_failure_stops_no_write(self):
        before = self.store.snapshot_sha256()
        self.store.writable = True
        with patch.object(self.memory.embeddings, 'encode', side_effect=ValueError('token budget')):
            with self.assertRaises(MemoryServiceError):
                self.client.add('over-tokens', 'word '*300, {'source': {'test_only': True}})
        self.assertEqual(before, self.store.snapshot_sha256())
    def test_syntax_and_imports(self):
        for name in ('validation/accept_retrieval_prompt.py', 'validation/count_memory_candidates.py',
                     'validation/memory_service_session.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'chromadb', 'transformers')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
