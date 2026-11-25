"""M20 stdlib-only memory primitives. Not connected to the driving loop."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

OWNER = Path('/home/nclab/Yizhen')
MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '717413c64de70e37b55cf53c9cdff0e2d331fac3'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def personal_path(path):
    """Production boundary; tests replace OWNER with their own temporary root."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Absolute personal path required')
    resolved = path.resolve()
    resolved.relative_to(OWNER.resolve())
    if resolved == OWNER.resolve():
        raise ValueError('A child path is required')
    return resolved


def manifest(query_schema, scene='intersection-multi-agent-v0'):
    if not isinstance(query_schema, str) or not query_schema.strip():
        raise ValueError('Explicit query schema required')
    return dict(format_version=1, model=MODEL, revision=REVISION, dimension=384,
                pooling='attention-mask-mean', normalization='l2',
                max_tokens=256, truncation='reject', query_schema=query_schema,
                scene=scene, metric='cosine')


def validate_manifest(value):
    if not isinstance(value, dict) or value != manifest(value.get('query_schema'), value.get('scene')):
        raise ValueError('Unsupported memory manifest')
    if value['scene'] != 'intersection-multi-agent-v0':
        raise ValueError('Unsupported memory scene')
    return json.loads(canonical(value))


def vector(value, dimension):
    if not isinstance(value, list) or len(value) != dimension:
        raise ValueError('Embedding dimension mismatch')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError('Non-finite/non-numeric embedding')
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0 or abs(norm-1) > 1e-4:
        raise ValueError('Expected a finite L2-normalized nonzero embedding')
    return [float(x) for x in value]


def texts_checked(texts):
    if (not isinstance(texts, list) or not 1 <= len(texts) <= 32 or
            any(not isinstance(t, str) or not t.strip() or len(t) > 16384 for t in texts)):
        raise ValueError('Expected 1..32 nonempty texts, at most 16384 characters each')
    return texts


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError('Embedding redirects forbidden')


class LocalEmbedding:
    def __init__(self, expected_manifest, port=18081, timeout=30):
        self.manifest = validate_manifest(expected_manifest)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid embedding port')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Invalid embedding timeout')
        self.url = 'http://127.0.0.1:{}/embed'.format(port)
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def encode(self, texts):
        texts_checked(texts)
        body = canonical(dict(manifest=self.manifest, texts=texts)).encode('utf-8')
        request = Request(self.url, data=body, headers={'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(8*1024*1024+1)
        if len(raw) > 8*1024*1024:
            raise ValueError('Embedding response too large')
        result = json.loads(raw.decode('utf-8'))
        if result.get('manifest') != self.manifest:
            raise ValueError('Embedding service manifest mismatch')
        rows = result.get('data')
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError('Embedding response count mismatch')
        vectors = []
        for index, (row, text) in enumerate(zip(rows, texts)):
            if (type(row.get('index')) is not int or row['index'] != index or
                    row.get('text_sha256') != text_hash(text)):
                raise ValueError('Embedding response input order mismatch')
            vectors.append(vector(row.get('embedding'), self.manifest['dimension']))
        return vectors


class MemoryStore:
    """Small-corpus exact cosine search; scores are not safety probabilities.

    Existing stores open read-only by default. Creation is explicit and refuses
    overwriting any existing file. No legacy Chroma migration is performed.
    """
    def __init__(self, path, expected_manifest, *, create=False, writable=False):
        self.manifest = validate_manifest(expected_manifest)
        self.path = personal_path(path)
        self.writable = writable or create
        self.connection = None
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('xb'):
                pass
        elif not self.path.is_file():
            raise ValueError('Memory database does not exist')
        try:
            mode = 'rw' if self.writable else 'ro'
            self.connection = sqlite3.connect(self.path.as_uri()+'?mode='+mode, uri=True)
            if create:
                with self.connection:
                    self.connection.execute('CREATE TABLE manifest (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
                    self.connection.execute('INSERT INTO manifest VALUES (1, ?)', (canonical(self.manifest),))
                    self.connection.execute('CREATE TABLE memories (id TEXT PRIMARY KEY, text TEXT NOT NULL, metadata TEXT NOT NULL, embedding TEXT NOT NULL)')
            rows = self.connection.execute('SELECT value FROM manifest ORDER BY id').fetchall()
            if rows != [(canonical(self.manifest),)]:
                raise ValueError('Database manifest mismatch')
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def add(self, memory_id, text, metadata, embedding):
        if not self.writable:
            raise ValueError('Read-only memory')
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError('Explicit memory ID required')
        texts_checked([text])
        if not isinstance(metadata, dict) or not isinstance(metadata.get('source'), dict) or not metadata['source']:
            raise ValueError('Explicit source metadata required')
        encoded = vector(embedding, self.manifest['dimension'])
        with self.connection:
            self.connection.execute('INSERT INTO memories VALUES (?, ?, ?, ?)',
                                    (memory_id, text, canonical(metadata), canonical(encoded)))

    def search(self, embedding, top_k=2):
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError('top_k must be 1..100')
        query = vector(embedding, self.manifest['dimension'])
        results = []
        for memory_id, text, metadata, raw in self.connection.execute('SELECT id,text,metadata,embedding FROM memories'):
            saved = vector(json.loads(raw), self.manifest['dimension'])
            # Divide by actual norms, even within the normalization tolerance.
            score = math.fsum(a*b for a, b in zip(query, saved))/(math.hypot(*query)*math.hypot(*saved))
            results.append(dict(id=memory_id, text=text, metadata=json.loads(metadata),
                                score=max(-1., min(1., score))))
        return sorted(results, key=lambda r: (-r['score'], r['id']))[:top_k]

    def snapshot_sha256(self):
        """Logical corpus hash, stable across SQLite page layout differences."""
        rows = self.connection.execute('SELECT id,text,metadata,embedding FROM memories ORDER BY id').fetchall()
        return hashlib.sha256(canonical(dict(manifest=self.manifest, rows=rows)).encode('utf-8')).hexdigest()


class LocalMemory:
    """Text-level adapter; caller supplies versioned query text and source data."""
    def __init__(self, store, embeddings):
        if store.manifest != embeddings.manifest:
            raise ValueError('Client/store manifest mismatch')
        self.store, self.embeddings = store, embeddings

    def retrieve(self, query, top_k=2):
        texts_checked([query])
        return self.store.search(self.embeddings.encode([query])[0], top_k)

    def add(self, memory_id, text, metadata):
        if not self.store.writable:
            raise ValueError('Read-only memory')
        self.store.add(memory_id, text, metadata, self.embeddings.encode([text])[0])
