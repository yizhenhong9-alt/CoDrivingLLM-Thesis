"""Windows stdlib doubles only; no real Chroma/model imports."""
import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as lm
from llm_controller.memory_http import MemoryHTTPClient, MemoryServiceError
from validation.serve_local_memory import make_handler


class Store:
    writable = True
    def __init__(self):
        self.rows = {}
    def snapshot_sha256(self):
        return lm.text_hash(lm.canonical(self.rows))


class Memory:
    def __init__(self, expected):
        self.store = Store()
        self.manifest = expected
    def add(self, memory_id, text, metadata):
        if not self.store.writable or memory_id in self.store.rows:
            raise ValueError('No write')
        self.store.rows[memory_id] = dict(id=memory_id, text=text, metadata=metadata,
                                         distance=0., score=1.)
    def retrieve(self, query, top_k=2):
        return list(self.store.rows.values())[:top_k]


class Tests(unittest.TestCase):
    def setUp(self):
        self.expected = lm.manifest('r7-test')
        self.memory = Memory(self.expected)
        self.server = HTTPServer(('127.0.0.1', 0), make_handler(self.expected, self.memory))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = MemoryHTTPClient(self.expected, self.server.server_port)
        self.meta = dict(human_question='None', negotiation_result='None', final_action='[3]',
                         comments='recommended to FASTER', source=dict(test_only=True))
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def test_roundtrip_empty_source_id_and_original_values(self):
        self.assertEqual(self.client.retrieve('\n Conflict info is empty'), [])
        self.client.add('original', ' Conflict info is empty', self.meta)
        hit = self.client.retrieve('\n Conflict info is empty')[0]
        self.assertEqual(hit['metadata'], self.meta)
        self.assertEqual(hit['text'], ' Conflict info is empty')
        self.assertEqual(hit['id'], 'original')
        self.assertTrue(self.client.status()['writable'])
    def test_duplicate_and_readonly_propagate_without_retry(self):
        self.client.add('one', 'text', self.meta)
        with self.assertRaises(MemoryServiceError):
            self.client.add('one', 'text', self.meta)
        self.memory.store.writable = False
        with self.assertRaises(MemoryServiceError):
            self.client.add('two', 'text', self.meta)
        self.assertEqual(len(self.memory.store.rows), 1)
    def test_manifest_mismatch(self):
        with self.assertRaises(MemoryServiceError):
            MemoryHTTPClient(lm.manifest('wrong'), self.server.server_port).status()
    def test_invalid_inputs(self):
        for metadata in ({}, {'source': {}}, {'source': 'invalid'}):
            with self.assertRaises(ValueError):
                self.client.add('id', 'text', metadata)
        for k in (0, True, 101):
            with self.assertRaises(ValueError):
                self.client.retrieve('text', k)
    def test_backend_failure_not_empty_hits_no_sensitive_logging(self):
        output = io.StringIO()
        with patch.object(self.memory, 'retrieve', side_effect=RuntimeError('SECRET text')):
            with contextlib.redirect_stderr(output), self.assertRaises(MemoryServiceError) as error:
                self.client.retrieve('SECRET query')
        self.assertNotIn('SECRET', str(error.exception)+output.getvalue())
    def test_response_corruption_rejected(self):
        self.client.add('one', 'text', self.meta)
        for key, value in [('score', float('inf')), ('metadata', {}), ('id', '')]:
            with patch.dict(self.memory.store.rows['one'], {key: value}):
                with self.assertRaises((ValueError, MemoryServiceError)):
                    self.client.retrieve('text')
        with patch.object(self.client, '_call', return_value={'id': 'wrong'}):
            with self.assertRaises(ValueError):
                self.client.add('one', 'text', self.meta)
    def test_no_proxy_redirect_and_size_guards(self):
        from urllib.request import ProxyHandler
        self.assertFalse(any(isinstance(h, ProxyHandler) and h.proxies for h in self.client.opener.handlers))
        with self.assertRaises(ValueError):
            lm.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')
        with self.assertRaises(ValueError):
            self.client.add('id', 'text', dict(source={'large': 'x'*1048576}))
    def test_wrong_query_hash_duplicate_ids_distance(self):
        row = dict(id='one', text='text', metadata=self.meta, distance=0., score=1.)
        for payload in (dict(query_sha256='wrong', hits=[]),
                        dict(query_sha256=lm.text_hash('text'), hits=[row, row]),
                        dict(query_sha256=lm.text_hash('text'), hits=[dict(row, distance=3.)])):
            with patch.object(self.client, '_call', return_value=payload):
                with self.assertRaises(ValueError):
                    self.client.retrieve('text')
    def test_python38_and_no_ml_import(self):
        for name in ('llm_controller/memory_http.py', 'validation/serve_local_memory.py',
                     'validation/accept_memory_http.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'chromadb', 'transformers')))

    def test_http_to_localmemory_to_chroma_double(self):
        from validation.check_chroma_memory import FakeClient
        from validation.check_local_memory import unit
        from llm_controller.chroma_memory import ChromaMemoryStore
        with tempfile.TemporaryDirectory() as temp, patch.object(lm, 'OWNER', Path(temp)):
            fake = FakeClient()
            with ChromaMemoryStore(Path(temp)/'db', self.expected, create=True,
                                   _client_factory=lambda path: fake) as store:
                class Encoder:
                    manifest = self.expected
                    def encode(self, texts):
                        return [unit() for text in texts]
                memory = lm.LocalMemory(store, Encoder())
                self.server.RequestHandlerClass = make_handler(self.expected, memory)
                self.client.add('chroma-id', 'original text', self.meta)
                hit = self.client.retrieve('\noriginal text')[0]
                self.assertEqual(hit['id'], 'chroma-id')
                self.assertEqual(hit['metadata'], self.meta)
                self.assertEqual(fake.embedding_functions, [None])
                self.assertEqual(len(fake.collection.queries), 1)

    def test_framing_and_transport_failure(self):
        import http.client
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('POST', '/status', body=b'{}', headers={'Transfer-Encoding': 'chunked'})
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()
        with patch.object(self.client.opener, 'open', side_effect=TimeoutError('SECRET')):
            with self.assertRaises(MemoryServiceError) as error:
                self.client.add('id', 'text', self.meta)
        self.assertNotIn('SECRET', str(error.exception))

    def test_verified_snapshot_rejects_corrupt_receipts_without_ml(self):
        from validation.serve_local_memory import verified_snapshot
        from llm_controller.local_memory import REVISION
        from validation.accept_minilm_embedding import FILES
        with tempfile.TemporaryDirectory() as temp, patch.object(lm, 'OWNER', Path(temp)):
            run = Path(temp)/'r6'
            run.mkdir()
            info = dict(sha=REVISION, siblings=[dict(rfilename=name, size=1, blobId='a'*40) for name in FILES])
            (run/'source-api.json').write_text(json.dumps(info))
            (run/'download.json').write_text(json.dumps(dict(files={}, revision=REVISION)))
            with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
                verified_snapshot(run)


if __name__ == '__main__':
    unittest.main(verbosity=2)
