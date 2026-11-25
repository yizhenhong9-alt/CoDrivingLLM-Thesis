"""M20-R1 contract tests using explicit Chroma doubles, never a local model.

--real-chroma adds a Spark-only persistent roundtrip, still with synthetic vectors.
"""
import ast
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as m
from llm_controller.chroma_memory import ChromaMemoryStore, _production_client
from validation.check_local_memory import unit

RUN_REAL = '--real-chroma' in sys.argv
if RUN_REAL:
    sys.argv.remove('--real-chroma')
    if sys.platform != 'linux':
        raise RuntimeError('--real-chroma is only permitted manually on Spark')


class FakeCollection:
    def __init__(self, metadata):
        self.metadata = copy.deepcopy(metadata)
        self.rows = {}
        self.queries = []

    def count(self):
        return len(self.rows)

    def add(self, *, ids, documents, metadatas, embeddings):
        for key, text, meta, vec in zip(ids, documents, metadatas, embeddings):
            # Mirror the important legacy risk: duplicate IDs can be ignored.
            if key not in self.rows:
                self.rows[key] = (text, meta, vec)

    def get(self, *, include, ids=None):
        keys = [key for key in (ids if ids is not None else self.rows) if key in self.rows]
        return dict(ids=keys, documents=[self.rows[k][0] for k in keys],
                    metadatas=[self.rows[k][1] for k in keys],
                    embeddings=[self.rows[k][2] for k in keys])

    def query(self, *, query_embeddings, n_results, include):
        self.queries.append(copy.deepcopy(query_embeddings))
        query = query_embeddings[0]
        rows = sorted(((1-math.fsum(a*b for a, b in zip(query, row[2])), key, row)
                       for key, row in self.rows.items()))[:n_results]
        return dict(ids=[[key for _, key, _ in rows]],
                    documents=[[row[0] for _, _, row in rows]],
                    metadatas=[[row[1] for _, _, row in rows]],
                    distances=[[distance for distance, _, _ in rows]])


class FakeClient:
    def __init__(self):
        self.collection = None
        self.embedding_functions = []

    def create_collection(self, *, name, metadata, embedding_function):
        self.embedding_functions.append(embedding_function)
        if self.collection is not None:
            raise ValueError('Collection exists')
        self.collection = FakeCollection(metadata)
        return self.collection

    def get_collection(self, *, name, embedding_function):
        self.embedding_functions.append(embedding_function)
        if self.collection is None:
            raise ValueError('Missing collection')
        return self.collection


class ChromaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.owner = patch.object(m, 'OWNER', self.root)
        self.owner.start()
        self.path = self.root/'chroma'
        self.spec = m.manifest('synthetic-v1')
        self.fake = FakeClient()

    def tearDown(self):
        self.owner.stop()
        self.temp.cleanup()

    def store(self, **kwargs):
        return ChromaMemoryStore(self.path, self.spec,
                                 _client_factory=lambda path: self.fake, **kwargs)

    def test_roundtrip_and_explicit_embeddings(self):
        with self.store(create=True) as store:
            for key, vec in [('a', unit()), ('b', unit(1)), ('c', unit(sign=-1))]:
                store.add(key, 'scenario '+key, {'source': {'run': 'synthetic'}}, vec)
            rows = store.search(unit(), 3)
            self.assertEqual([r['id'] for r in rows], ['a', 'b', 'c'])
            self.assertEqual([r['distance'] for r in rows], [0., 1., 2.])
            self.assertEqual([r['score'] for r in rows], [1., 0., -1.])
            self.assertEqual(rows[0]['metadata']['source']['run'], 'synthetic')
            digest = store.snapshot_sha256()
        with self.store() as store:
            self.assertEqual(digest, store.snapshot_sha256())
        self.assertEqual(self.fake.embedding_functions, [None, None])
        self.assertFalse((self.path/'writer.lock').exists())

    def test_sqlite_candidate_parity_for_fixture(self):
        with self.store(create=True) as chroma, m.MemoryStore(self.root/'reference.sqlite3', self.spec, create=True) as sql:
            for key, vec in [('b', unit()), ('a', unit()), ('c', unit(1))]:
                for store in (chroma, sql):
                    store.add(key, 'text '+key, {'source': {'run': 'synthetic'}}, vec)
            self.assertEqual([r['id'] for r in chroma.search(unit())],
                             [r['id'] for r in sql.search(unit())])

    def test_text_adapter_uses_local_encoder(self):
        calls = []
        class Encoder:
            manifest = self.spec

            def encode(self, texts):
                calls.append(texts)
                return [unit() for _ in texts]
        with self.store(create=True) as store:
            memory = m.LocalMemory(store, Encoder())
            memory.add('a', 'past', {'source': {'run': 'synthetic'}})
            self.assertEqual(memory.retrieve('current')[0]['text'], 'past')
        self.assertEqual(calls, [['past'], ['current']])

    def test_original_fields_survive_metadata_envelope(self):
        fixture = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))
        with self.store(create=True) as store:
            for index, row in enumerate(fixture['rows']):
                original = row['would_write']
                metadata = dict(original['metadata'], source={'run': 'M16-replay-fixture-not-training',
                                                             'step': row['step_id'], 'vehicle': row['vehicle_id']})
                store.add('original-'+str(index), original['page_content'], metadata, unit(index))
                found = store.search(unit(index), 1)[0]
                self.assertEqual(found['text'], original['page_content'])
                self.assertEqual({key: found['metadata'][key] for key in original['metadata']}, original['metadata'])
                self.assertEqual(row['query'], '\n'+found['text'])
                self.assertEqual(found['metadata']['negotiation_result'], 'None')

    def test_duplicate_is_rejected_before_backend_add(self):
        with self.store(create=True) as store:
            store.add('a', 'original', {'source': {'run': 'synthetic'}}, unit())
            before = store.snapshot_sha256()
            with self.assertRaises(ValueError):
                store.add('a', 'replacement', {'source': {'run': 'synthetic'}}, unit(1))
            self.assertEqual(before, store.snapshot_sha256())

    def test_empty_small_corpus_and_invalid_inputs(self):
        with self.store(create=True) as store:
            self.assertEqual(store.search(unit()), [])
            for vec in ([0.]*384, [float('nan')]*384, [1.]):
                with self.assertRaises(ValueError):
                    store.search(vec)
            for k in (0, True, 101):
                with self.assertRaises(ValueError):
                    store.search(unit(), k)
            with self.assertRaises(ValueError):
                store.add('a', 'text', {}, unit())
            store.add('a', 'text', {'source': {'run': 'synthetic'}}, unit())
            self.assertEqual(len(store.search(unit(), 10)), 1)

    def test_no_overwrite_and_missing_path(self):
        with self.assertRaises(ValueError):
            self.store()
        self.assertFalse(self.path.exists())
        with self.store(create=True):
            pass
        with self.assertRaises(FileExistsError):
            self.store(create=True)

    def test_readonly_is_adapter_guard(self):
        with self.store(create=True):
            pass
        with self.store() as store:
            with self.assertRaises(ValueError):
                store.add('a', 'text', {'source': {'run': 'synthetic'}}, unit())

    def test_manifest_and_metric_mismatch(self):
        with self.store(create=True):
            pass
        with self.assertRaises(ValueError):
            ChromaMemoryStore(self.path, m.manifest('other'),
                              _client_factory=lambda path: self.fail('must fail before opening client'))
        self.fake.collection.metadata['hnsw:space'] = 'l2'
        with self.assertRaises(ValueError):
            self.store()

    def test_writer_lock_and_closed_guard(self):
        with self.store(create=True) as first:
            with self.assertRaises(FileExistsError):
                self.store(writable=True)
            self.assertTrue((self.path/'writer.lock').exists())
        with self.assertRaises(ValueError):
            first.search(unit())
        with self.store(writable=True):
            pass

    def test_backend_failure_releases_owned_lock(self):
        with self.store(create=True):
            pass
        with self.assertRaises(RuntimeError):
            ChromaMemoryStore(self.path, self.spec, writable=True,
                              _client_factory=lambda path: (_ for _ in ()).throw(RuntimeError('fixture')))
        self.assertFalse((self.path/'writer.lock').exists())

    def test_invalid_query_response_is_rejected(self):
        with self.store(create=True) as store:
            store.add('a', 'text', {'source': {'run': 'synthetic'}}, unit())
            original = self.fake.collection.query
            for bad in (dict(ids=[[]]), dict(distances=[[float('nan')]]), dict(distances=[[4.]])):
                def changed(**kwargs):
                    result = original(**kwargs)
                    result.update(bad)
                    return result
                with patch.object(self.fake.collection, 'query', side_effect=changed), self.assertRaises(ValueError):
                    store.search(unit())

    def test_lazy_import_python38_and_path_boundary(self):
        ast.parse((ROOT/'llm_controller/chroma_memory.py').read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('chromadb', 'langchain', 'openai', 'torch', 'transformers')))
        with self.assertRaises(ValueError):
            ChromaMemoryStore(self.root.parent/'outside', self.spec, create=True)

    @unittest.skipUnless(RUN_REAL, 'Real Chroma test is manual Spark-only; use --real-chroma')
    def test_real_chroma_persistence_with_synthetic_vectors(self):
        fixture = json.loads((ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_text(encoding='utf-8'))
        with ChromaMemoryStore(self.path, self.spec, create=True) as store:
            for index, row in enumerate(fixture['rows']):
                original = row['would_write']
                store.add('fixture-a' if index == 0 else 'fixture-b', original['page_content'],
                          dict(original['metadata'], source={'run': 'M20-R3-off-replay-fixture-not-training'}), unit(index))
            self.assertEqual(store.search(unit(), 2)[0]['id'], 'fixture-a')
        with ChromaMemoryStore(self.path, self.spec) as store:
            found = store.search(unit())[0]
            self.assertEqual(found['text'], fixture['rows'][0]['would_write']['page_content'])
            for key, value in fixture['rows'][0]['would_write']['metadata'].items():
                self.assertEqual(found['metadata'][key], value)
        # Reopen in a fresh Python process to avoid mistaking a cached client
        # for proof that on-disk records can actually be recovered.
        code = '''
import json, sys
from llm_controller.local_memory import manifest
from llm_controller.chroma_memory import ChromaMemoryStore
query = [1.0]+[0.0]*383
with ChromaMemoryStore(sys.argv[1], manifest('synthetic-v1')) as store:
    print(json.dumps(store.search(query, 1)[0], ensure_ascii=False))
'''
        environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
        child = subprocess.run([sys.executable, '-c', code, str(self.path)],
                               env=environment, cwd=str(ROOT), capture_output=True,
                               text=True, timeout=120)
        self.assertEqual(child.returncode, 0, child.stdout+'\n'+child.stderr)
        found = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual(found['id'], 'fixture-a')
        self.assertEqual(found['text'], fixture['rows'][0]['would_write']['page_content'])
        for key, value in fixture['rows'][0]['would_write']['metadata'].items():
            self.assertEqual(found['metadata'][key], value)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
