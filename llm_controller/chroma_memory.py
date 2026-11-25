"""M20-R1 Chroma backend with explicit external local embeddings.

No Chroma, LangChain, OpenAI or ML imports at module import time.
Evaluation is read-only at this adapter's API, not at Chroma's file layer.
"""
import hashlib
import json
import math
import sys

from .local_memory import (canonical, personal_path, validate_manifest, vector,
                           texts_checked)

CHROMA_VERSION = '0.4.15'
COLLECTION = 'codriving_local_m20'


def _stored_vector(value, dimension):
    # Chroma versions/backends may return NumPy arrays or plain Python lists.
    if hasattr(value, 'tolist'):
        value = value.tolist()
    return vector(value, dimension)


def _production_client(path):
    if sys.platform != 'linux':
        raise RuntimeError('Real Chroma is only opened manually on Spark Linux')
    import chromadb
    from chromadb.config import Settings
    if chromadb.__version__ != CHROMA_VERSION:
        raise ValueError('Expected chromadb=='+CHROMA_VERSION)
    return chromadb.PersistentClient(path=str(path), settings=Settings(
        anonymized_telemetry=False, allow_reset=False))


class ChromaMemoryStore:
    """Same vector-level interface as SQLite MemoryStore; one cooperating writer.

    _client_factory is a private test seam. Production does not use test doubles.
    Existing legacy Chroma directories are rejected; no implicit migration.
    close releases the application writer lock, not Chroma's internal resources.
    """
    def __init__(self, path, expected_manifest, *, create=False, writable=False,
                 _client_factory=None):
        self.manifest = validate_manifest(expected_manifest)
        self.path = personal_path(path)
        self.writable = writable or create
        self.collection = None
        self._lock = None
        self.closed = False
        self._metadata = {'hnsw:space': 'cosine',
                          'codriving:manifest': canonical(self.manifest),
                          'codriving:backend': 'M20-R1-chroma-'+CHROMA_VERSION}
        if create:
            self.path.mkdir(parents=True, exist_ok=False)
            # A failed creation deliberately leaves its directory for inspection.
            (self.path/'manifest.json').write_text(canonical(self.manifest)+'\n', encoding='utf-8')
        else:
            if not self.path.is_dir():
                raise ValueError('Chroma directory does not exist')
            for file in self.path.rglob('*'):
                personal_path(file)
            saved = json.loads((self.path/'manifest.json').read_text(encoding='utf-8'))
            if canonical(saved) != canonical(self.manifest):
                raise ValueError('Chroma directory manifest mismatch')
        try:
            if self.writable:
                lock = personal_path(self.path/'writer.lock')
                with lock.open('x', encoding='utf-8') as stream:
                    stream.write('M20-R1: cooperating writer; do not remove while active\n')
                self._lock = lock
            factory = _client_factory or _production_client
            self.client = factory(self.path)
            if create:
                self.collection = self.client.create_collection(
                    name=COLLECTION, metadata=self._metadata, embedding_function=None)
            else:
                self.collection = self.client.get_collection(
                    name=COLLECTION, embedding_function=None)
            self._check()
        except BaseException:
            self.close()
            raise

    def _check(self):
        if self.closed or self.collection is None:
            raise ValueError('Closed/uninitialized Chroma store')
        if self.collection.metadata != self._metadata:
            raise ValueError('Chroma collection manifest/metric mismatch')

    def close(self):
        self.closed = True
        if self._lock is not None:
            self._lock.unlink()
            self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def add(self, memory_id, text, metadata, embedding):
        self._check()
        if not self.writable:
            raise ValueError('Read-only memory adapter')
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError('Explicit memory ID required')
        texts_checked([text])
        if not isinstance(metadata, dict) or not isinstance(metadata.get('source'), dict) or not metadata['source']:
            raise ValueError('Explicit source metadata required')
        saved = vector(embedding, self.manifest['dimension'])
        encoded = {'codriving:metadata_json': canonical(metadata)}
        # 0.4.15 may ignore existing IDs instead of raising; check explicitly.
        if self.collection.get(ids=[memory_id], include=['metadatas'])['ids']:
            raise ValueError('Duplicate memory ID')
        self.collection.add(ids=[memory_id], documents=[text], metadatas=[encoded],
                            embeddings=[saved])
        result = self.collection.get(ids=[memory_id], include=['documents', 'metadatas', 'embeddings'])
        if (result['ids'] != [memory_id] or result['documents'] != [text] or
                result['metadatas'] != [encoded] or len(result['embeddings']) != 1):
            raise ValueError('Chroma write verification failed; do not retry blindly')
        returned = _stored_vector(result['embeddings'][0], self.manifest['dimension'])
        if any(abs(a-b) > 1e-5 for a, b in zip(saved, returned)):
            raise ValueError('Chroma embedding round-trip mismatch')

    def search(self, embedding, top_k=2):
        self._check()
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError('top_k must be 1..100')
        query = vector(embedding, self.manifest['dimension'])
        count = self.collection.count()
        if not count:
            return []
        size = min(count, top_k)
        result = self.collection.query(query_embeddings=[query], n_results=size,
                                       include=['documents', 'metadatas', 'distances'])
        columns = []
        for key in ('ids', 'documents', 'metadatas', 'distances'):
            column = result.get(key)
            if not isinstance(column, list) or len(column) != 1 or len(column[0]) != size:
                raise ValueError('Invalid Chroma query result shape')
            columns.append(column[0])
        rows, seen = [], set()
        for memory_id, text, metadata, distance in zip(*columns):
            if not isinstance(memory_id, str) or not memory_id or memory_id in seen:
                raise ValueError('Invalid/duplicate result ID')
            seen.add(memory_id)
            texts_checked([text])
            if type(distance) not in (int, float) or not math.isfinite(distance) or not -1e-5 <= distance <= 2+1e-5:
                raise ValueError('Invalid cosine distance')
            decoded = json.loads(metadata['codriving:metadata_json'])
            if not isinstance(decoded, dict) or not isinstance(decoded.get('source'), dict) or not decoded['source']:
                raise ValueError('Missing source metadata')
            rows.append(dict(id=memory_id, text=text, metadata=decoded,
                             distance=float(distance), score=max(-1., min(1., 1-distance))))
        # Deterministic order within returned candidates; HNSW boundary ties may differ.
        return sorted(rows, key=lambda row: (-row['score'], row['id']))

    def snapshot_sha256(self):
        """Logical snapshot; stop writers before calling for experiment evidence."""
        self._check()
        result = self.collection.get(include=['documents', 'metadatas', 'embeddings'])
        size = len(result['ids'])
        if any(len(result[key]) != size for key in ('documents', 'metadatas', 'embeddings')):
            raise ValueError('Invalid snapshot shape')
        rows = []
        for index, memory_id in enumerate(result['ids']):
            rows.append([memory_id, result['documents'][index], result['metadatas'][index],
                         _stored_vector(result['embeddings'][index], self.manifest['dimension'])])
        rows.sort(key=lambda row: row[0])
        return hashlib.sha256(canonical(dict(manifest=self.manifest, rows=rows,
                                             backend=self._metadata['codriving:backend'])).encode('utf-8')).hexdigest()
