"""M20-R7 stdlib-only loopback text memory protocol; no driving integration."""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

from .local_memory import (canonical, validate_manifest, texts_checked, text_hash,
                           NoRedirect)

LIMIT = 1024 * 1024


class MemoryServiceError(RuntimeError):
    """No automatic retries: a failed add may already have reached storage."""


def metadata_checked(metadata):
    if (not isinstance(metadata, dict) or
            not isinstance(metadata.get('source'), dict) or not metadata['source']):
        raise ValueError('Explicit source metadata required')
    canonical(metadata)
    return metadata


def id_checked(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError('Explicit bounded memory ID required')
    return value


def k_checked(value):
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError('top_k must be 1..100')
    return value


class MemoryHTTPClient:
    def __init__(self, expected_manifest, port=18082, timeout=30):
        self.manifest = validate_manifest(expected_manifest)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid memory port')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Invalid timeout')
        self.url = 'http://127.0.0.1:{}'.format(port)
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _call(self, operation, **fields):
        request = dict(protocol='m20-r7-v1', manifest=self.manifest, **fields)
        raw = canonical(request).encode('utf-8')
        if len(raw) > LIMIT:
            raise ValueError('Memory request too large')
        req = Request(self.url+'/'+operation, data=raw,
                      headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                payload = response.read(LIMIT+1)
        except HTTPError as exc:
            # Do not echo server body, query, ID or metadata into logs.
            code = exc.code
            exc.close()
            raise MemoryServiceError('Memory service HTTP {}; operation {}; write outcome may be unknown; do not retry blindly'.format(code, operation)) from None
        except (URLError, OSError):
            raise MemoryServiceError('Memory transport failed; operation {}; write outcome may be unknown; do not retry blindly'.format(operation)) from None
        if len(payload) > LIMIT:
            raise ValueError('Memory response too large')
        result = json.loads(payload.decode('utf-8'))
        if (not isinstance(result, dict) or result.get('protocol') != 'm20-r7-v1' or
                result.get('manifest') != self.manifest or result.get('operation') != operation):
            raise ValueError('Memory response identity mismatch')
        return result

    def status(self):
        return self._call('status')

    def add(self, memory_id, text, metadata):
        id_checked(memory_id)
        texts_checked([text])
        metadata_checked(metadata)
        result = self._call('add', id=memory_id, text=text, metadata=metadata)
        if (result.get('id') != memory_id or result.get('text_sha256') != text_hash(text) or
                result.get('metadata_sha256') != text_hash(canonical(metadata))):
            raise ValueError('Memory write receipt mismatch; do not retry blindly')
        return result

    def retrieve(self, query, top_k=2):
        texts_checked([query])
        k_checked(top_k)
        result = self._call('retrieve', query=query, top_k=top_k)
        hits = result.get('hits')
        if (result.get('query_sha256') != text_hash(query) or
                not isinstance(hits, list) or len(hits) > top_k):
            raise ValueError('Memory query receipt mismatch')
        seen = set()
        for hit in hits:
            memory_id = id_checked(hit['id'])
            if memory_id in seen:
                raise ValueError('Duplicate result ID')
            seen.add(memory_id)
            texts_checked([hit['text']])
            metadata_checked(hit['metadata'])
            distance, score = hit['distance'], hit['score']
            if (type(distance) not in (int, float) or not math.isfinite(distance) or
                    not -1e-5 <= distance <= 2+1e-5 or
                    type(score) not in (int, float) or not math.isfinite(score) or
                    abs(score-max(-1., min(1., 1-distance))) > 1e-8):
                raise ValueError('Invalid result distance/score')
        return hits
