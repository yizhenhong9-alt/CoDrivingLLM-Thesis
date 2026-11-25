"""M20 offline tests: synthetic embeddings only; no ML dependencies loaded."""
import ast
from http.server import HTTPServer
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as m
from validation.serve_local_embedding import make_handler


def unit(index=0, sign=1):
    value = [0.]*384
    value[index] = sign
    return value


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.owner = patch.object(m, 'OWNER', self.root)
        self.owner.start()
        self.path = self.root/'memory'/'test.sqlite3'
        self.manifest = m.manifest('synthetic-v1')

    def tearDown(self):
        self.owner.stop()
        self.temp.cleanup()

    def create(self):
        return m.MemoryStore(self.path, self.manifest, create=True)

    def test_roundtrip_cosine_order_source_and_snapshot(self):
        with self.create() as store:
            empty_hash = store.snapshot_sha256()
            for key, vec in [('b', unit()), ('a', unit()), ('c', unit(1)), ('d', unit(sign=-1))]:
                store.add(key, 'scenario '+key, {'source': {'run': 'synthetic'}}, vec)
            results = store.search(unit(), 4)
            self.assertEqual([r['id'] for r in results], ['a', 'b', 'c', 'd'])
            self.assertEqual([r['score'] for r in results], [1., 1., 0., -1.])
            self.assertEqual(results[0]['metadata']['source']['run'], 'synthetic')
            saved_hash = store.snapshot_sha256()
            self.assertNotEqual(saved_hash, empty_hash)
        with m.MemoryStore(self.path, self.manifest) as store:
            self.assertEqual(store.snapshot_sha256(), saved_hash)
            self.assertEqual(len(store.search(unit())), 2)

    def test_empty_and_invalid_k(self):
        with self.create() as store:
            self.assertEqual(store.search(unit()), [])
            for k in (0, -1, True, 101, 1.5):
                with self.subTest(k=k), self.assertRaises(ValueError):
                    store.search(unit(), k)

    def test_duplicate_is_not_overwritten(self):
        with self.create() as store:
            store.add('a', 'original', {'source': {'run': 'synthetic'}}, unit())
            before = store.snapshot_sha256()
            with self.assertRaises(sqlite3.IntegrityError):
                store.add('a', 'replacement', {'source': {'run': 'other'}}, unit(1))
            self.assertEqual(store.snapshot_sha256(), before)

    def test_readonly_and_no_implicit_creation(self):
        with self.assertRaises(ValueError):
            m.MemoryStore(self.path, self.manifest)
        self.assertFalse(self.path.parent.exists())
        with self.create():
            pass
        with m.MemoryStore(self.path, self.manifest) as store:
            with self.assertRaises(ValueError):
                store.add('a', 'text', {'source': {'run': 'x'}}, unit())
            with self.assertRaises(sqlite3.OperationalError):
                store.connection.execute("DELETE FROM manifest")

    def test_create_refuses_existing(self):
        with self.create():
            pass
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(before, self.path.read_bytes())

    def test_database_manifest_mismatch(self):
        with self.create():
            pass
        with self.assertRaises(ValueError):
            m.MemoryStore(self.path, m.manifest('other-v1'))

    def test_invalid_vectors_and_metadata_never_write(self):
        with self.create() as store:
            for vec in ([1.], [0.]*384, [float('nan')]*384,
                        [float('inf')]*384, [True]*384, [1.]*384):
                with self.subTest(vec=str(vec)[:30]), self.assertRaises(ValueError):
                    store.add('a', 'text', {'source': {'run': 'x'}}, vec)
            with self.assertRaises(ValueError):
                store.add('a', 'text', {}, unit())
            self.assertEqual(store.search(unit()), [])

    def test_path_escape_and_relative_rejected(self):
        for path in ('relative.sqlite3', self.root.parent/'outside.sqlite3', self.root):
            with self.subTest(path=path), self.assertRaises(ValueError):
                m.personal_path(path)

    def test_symlink_escape(self):
        link = self.root/'escape'
        try:
            link.symlink_to(self.root.parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest('OS does not permit symlink creation: '+str(exc))
        with self.assertRaises(ValueError):
            m.personal_path(link/'outside.sqlite3')

    def test_corrupt_vector_rejected_on_search(self):
        with self.create() as store:
            store.add('a', 'text', {'source': {'run': 'x'}}, unit())
            with store.connection:
                store.connection.execute("UPDATE memories SET embedding='[0]'")
            with self.assertRaises(ValueError):
                store.search(unit())

    def test_text_adapter_and_manifest_guard(self):
        class FakeEmbedding:
            manifest = self.manifest

            def encode(self, texts):
                return [unit() for text in texts]
        with self.create() as store:
            memory = m.LocalMemory(store, FakeEmbedding())
            memory.add('a', 'past situation', {'source': {'run': 'synthetic'}})
            self.assertEqual(memory.retrieve('current situation')[0]['id'], 'a')
            fake = FakeEmbedding()
            fake.manifest = m.manifest('different')
            with self.assertRaises(ValueError):
                m.LocalMemory(store, fake)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.manifest = m.manifest('synthetic-v1')
        self.client = m.LocalEmbedding(self.manifest)

    def response(self, **changes):
        result = dict(manifest=self.manifest,
                      data=[dict(index=0, text_sha256=m.text_hash('hello'), embedding=unit())])
        result.update(changes)
        self.client.opener = type('Fake', (), {'open': lambda *_args, **_kw:
                                              io.BytesIO(json.dumps(result).encode())})()

    def test_response_checks(self):
        self.response()
        self.assertEqual(self.client.encode(['hello']), [unit()])
        for change in (dict(manifest=m.manifest('other')), dict(data=[]),
                       dict(data=[dict(index=1, text_sha256=m.text_hash('hello'), embedding=unit())]),
                       dict(data=[dict(index=0, text_sha256=m.text_hash('different'), embedding=unit())]),
                       dict(data=[dict(index=0, text_sha256=m.text_hash('hello'), embedding=[0.]*384)])):
            self.response(**change)
            with self.assertRaises(ValueError):
                self.client.encode(['hello'])

    def test_config_and_text_validation(self):
        for kwargs in (dict(port=True), dict(port=0), dict(timeout=float('nan')), dict(timeout=0)):
            with self.assertRaises(ValueError):
                m.LocalEmbedding(self.manifest, **kwargs)
        for texts in ([], [''], ['  '], 'hello', ['x'*16385]):
            with self.assertRaises(ValueError):
                self.client.encode(texts)
        for field, value in [('revision', 'main'), ('dimension', 768), ('pooling', 'cls')]:
            changed = dict(self.manifest, **{field: value})
            with self.assertRaises(ValueError):
                m.LocalEmbedding(changed)

    def test_redirect_and_proxy_policy(self):
        with self.assertRaises(ValueError):
            m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')
        with patch.dict('os.environ', {'http_proxy': 'http://invalid:9', 'https_proxy': 'http://invalid:9'}):
            client = m.LocalEmbedding(self.manifest)
            self.assertFalse(any(getattr(handler, 'proxies', {}) for handler in client.opener.handlers))

    def test_real_loopback_http_with_fake_encoder(self):
        server = HTTPServer(('127.0.0.1', 0), make_handler(self.manifest, lambda texts: [unit(i) for i in range(len(texts))]))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = m.LocalEmbedding(self.manifest, port=server.server_port)
            self.assertEqual(client.encode(['one', 'two']), [unit(0), unit(1)])
            wrong = m.LocalEmbedding(m.manifest('other'), port=server.server_port)
            with self.assertRaises(HTTPError):
                wrong.encode(['one'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_python38_syntax_and_no_ml_imports(self):
        for file in ('llm_controller/local_memory.py', 'validation/serve_local_embedding.py'):
            ast.parse((ROOT/file).read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'transformers', 'langchain', 'chromadb')))


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
