"""M20-R6: Spark-only pinned download and offline real-vector acceptance."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import MODEL, REVISION, manifest, personal_path, vector

FILES = ('config.json', 'model.safetensors', 'tokenizer.json',
         'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt',
         'sentence_bert_config.json', '1_Pooling/config.json', 'modules.json')


def select_files(info):
    if info.get('sha') != REVISION:
        raise ValueError('Model API revision mismatch')
    siblings = {item['rfilename']: item for item in info['siblings']}
    selected = {}
    for name in FILES:
        item = siblings[name]  # Missing safetensors/config stops; no main/pickle fallback.
        lfs = item.get('lfs')
        size = lfs['size'] if lfs else item['size']
        digest = lfs['sha256'] if lfs else item['blobId']
        algorithm = 'sha256' if lfs else 'git-sha1'
        expected_length = 64 if lfs else 40
        if (type(size) is not int or not 0 < size <= 512*1024*1024 or
                not isinstance(digest, str) or len(digest) != expected_length or
                any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Invalid source size/hash')
        selected[name] = dict(size=size, digest=digest, algorithm=algorithm)
    return selected


def verify_file(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected['size']:
        raise ValueError('File size/type mismatch: '+str(path))
    source = hashlib.sha256() if expected['algorithm'] == 'sha256' else hashlib.sha1()
    if expected['algorithm'] == 'git-sha1':
        source.update(('blob '+str(expected['size'])+'\0').encode())
    sha256 = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            source.update(chunk)
            sha256.update(chunk)
    if source.hexdigest() != expected['digest']:
        raise ValueError('Source hash mismatch: '+str(path))
    return sha256.hexdigest()


def fetch(url):
    if not url.startswith('https://huggingface.co/'):
        raise ValueError('Unexpected source URL')
    response = urllib.request.urlopen(url, timeout=120)
    if not response.geturl().startswith('https://'):
        response.close()
        raise ValueError('Non-HTTPS redirect')
    return response


def download(snapshot, run):
    api = 'https://huggingface.co/api/models/'+MODEL+'/revision/'+REVISION+'?blobs=true'
    with fetch(api) as response:
        raw = response.read(4*1024*1024+1)
    if len(raw) > 4*1024*1024:
        raise ValueError('Oversized metadata')
    info = json.loads(raw)
    selected = select_files(info)
    (run/'source-api.json').write_bytes(raw)
    snapshot.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, expected in selected.items():
        target = personal_path(snapshot/name)
        if target.exists():
            hashes[name] = verify_file(target, expected)
            continue
        partial = run/('download-'+name.replace('/', '_')+'.partial')
        url = 'https://huggingface.co/'+MODEL+'/resolve/'+REVISION+'/'+name
        with fetch(url) as response, partial.open('xb') as output:
            total = 0
            while True:
                chunk = response.read(1024*1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected['size']:
                    raise ValueError('Download exceeds declared size')
                output.write(chunk)
        hashes[name] = verify_file(partial, expected)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Hard link publishes without replacing an existing file, on the same filesystem.
        os.link(partial, target)
    receipt = dict(model=MODEL, revision=REVISION, files=selected, sha256=hashes)
    (run/'download.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def acceptance(snapshot, run, receipt):
    for name, expected in receipt['files'].items():
        if verify_file(snapshot/name, expected) != receipt['sha256'][name]:
            raise ValueError('Snapshot changed')
    config = json.loads((snapshot/'config.json').read_text())
    pooling = json.loads((snapshot/'1_Pooling/config.json').read_text())
    sentence = json.loads((snapshot/'sentence_bert_config.json').read_text())
    if (config.get('hidden_size') != 384 or config.get('model_type') != 'bert' or
            sentence.get('max_seq_length') != 256 or
            pooling.get('pooling_mode_mean_tokens') is not True or
            any(value is True for key, value in pooling.items()
                if key.startswith('pooling_mode_') and key != 'pooling_mode_mean_tokens')):
        raise ValueError('Source architecture/pooling differs from reviewed encoder')
    import torch
    torch.set_num_threads(1)
    if torch.version.cuda is not None:
        raise ValueError('CPU build required')
    from validation.serve_local_embedding import load_encoder
    from llm_controller.chroma_memory import ChromaMemoryStore
    expected = manifest('m20-r6-original-fixtures-v1')
    started = time.perf_counter()
    encode = load_encoder(snapshot, expected)
    cold_seconds = time.perf_counter()-started
    fixture_path = ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json'
    fixture_bytes = fixture_path.read_bytes()
    rows = json.loads(fixture_bytes)['rows']
    texts = [row['would_write']['page_content'] for row in rows]
    vectors = [vector(v, 384) for v in encode(texts)]
    if len(vectors) != len(rows):
        raise ValueError('Embedding count mismatch')
    query_vectors = [vector(v, 384) for v in encode([row['query'] for row in rows])]
    if len(query_vectors) != len(rows):
        raise ValueError('Query embedding count mismatch')
    singles = [vector(encode([text])[0], 384) for text in texts]
    max_batch_error = max(abs(a-b) for batch, single in zip(vectors, singles)
                          for a, b in zip(batch, single))
    if max_batch_error > 1e-5:
        raise ValueError('Batch/single mismatch')
    try:
        encode(['word '*300])
    except ValueError:
        pass
    else:
        raise ValueError('Oversized token input was not rejected')
    stored_metadata = []
    results = []
    database = run/'test-chroma'
    with ChromaMemoryStore(database, expected, create=True, writable=True) as store:
        for i, row in enumerate(rows):
            metadata = dict(row['would_write']['metadata'])
            metadata['source'] = dict(test_only=True, fixture_index=i,
                                      fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest())
            stored_metadata.append(metadata)
            store.add('fixture-'+str(i), texts[i], metadata, vectors[i])
        for i, query in enumerate(query_vectors):
            hits = store.search(query, top_k=2)
            if hits[0]['id'] != 'fixture-'+str(i) or hits[0]['metadata'] != stored_metadata[i]:
                raise ValueError('Original fixture retrieval/metadata mismatch')
            results.append(dict(query=rows[i]['query'], hits=hits))
        logical_hash = store.snapshot_sha256()
    with ChromaMemoryStore(database, expected) as store:
        if store.snapshot_sha256() != logical_hash:
            raise ValueError('Reopen logical snapshot changed')
        latency = []
        for _ in range(5):
            started = time.perf_counter()
            store.search(vector(encode([rows[0]['query']])[0], 384), top_k=2)
            latency.append((time.perf_counter()-started)*1000)
    result = dict(status='PASS', cold_load_seconds=cold_seconds,
                  batch_single_max_absolute_error=max_batch_error,
                  warm_encode_and_retrieve_ms=latency,
                  warm_median_ms=statistics.median(latency),
                  results=results, logical_snapshot_sha256=logical_hash,
                  limitation='Two isolated original fixtures; no traffic quality or production memory-on claim. Reopen is same-process.',
                  duplicate_empty_text_warning='Identical empty-conflict text cannot distinguish different past actions.')
    (run/'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != 'linux' or platform.machine() != 'aarch64' or
            Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312')):
        raise RuntimeError('Dedicated Spark ARM64 memory environment only')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    baseline = personal_path(Path('/home/nclab/Yizhen/runs/M20-R5-minilm-runtime-jhL8nq/runtime.json'))
    approved = json.loads(baseline.read_text())
    from validation.plan_minilm_runtime import name_key
    current = {name_key(d.metadata['Name']): d.version for d in importlib.metadata.distributions()}
    if approved['status'] != 'PASS' or current != approved['packages']:
        raise ValueError('Environment differs from accepted R5 runtime')
    snapshot = personal_path(Path('/home/nclab/Yizhen/models/all-MiniLM-L6-v2')/REVISION)
    receipt = download(snapshot, run)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    acceptance(snapshot, run, receipt)


if __name__ == '__main__':
    main()
