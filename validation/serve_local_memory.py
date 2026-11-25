"""M20-R7 single loopback encode -> Chroma service. Explicit Spark launch only."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import (canonical, manifest, personal_path,
                                         text_hash, texts_checked, REVISION)
from llm_controller.memory_http import LIMIT, metadata_checked, id_checked, k_checked


def make_handler(expected, memory):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if (self.headers.get('Transfer-Encoding') or len(lengths) != 1 or
                        not lengths[0].isdigit() or not 0 < int(lengths[0]) <= LIMIT):
                    raise ValueError('Invalid framing')
                raw = self.rfile.read(int(lengths[0]))
                if len(raw) != int(lengths[0]):
                    raise ValueError('Incomplete body')
                request = json.loads(raw.decode('utf-8'))
                if (not isinstance(request, dict) or request.get('manifest') != expected or
                        request.get('protocol') != 'm20-r7-v1'):
                    raise ValueError('Identity mismatch')
                operation = self.path[1:]
                body = dict(protocol='m20-r7-v1', manifest=expected, operation=operation)
                if self.path == '/status':
                    body.update(writable=memory.store.writable,
                                snapshot_sha256=memory.store.snapshot_sha256())
                elif self.path == '/retrieve':
                    query = texts_checked([request.get('query')])[0]
                    k = k_checked(request.get('top_k'))
                    body.update(query_sha256=text_hash(query), hits=memory.retrieve(query, k))
                elif self.path == '/add':
                    memory_id = id_checked(request.get('id'))
                    text = texts_checked([request.get('text')])[0]
                    metadata = metadata_checked(request.get('metadata'))
                    memory.add(memory_id, text, metadata)
                    body.update(id=memory_id, text_sha256=text_hash(text),
                                metadata_sha256=text_hash(canonical(metadata)))
                else:
                    raise ValueError('Unknown endpoint')
                payload = canonical(body).encode('utf-8')
                if len(payload) > LIMIT:
                    raise ValueError('Response too large')
                status = 200
            except Exception as exc:
                # Backend errors are failures, never empty hits or successful writes.
                status = 400 if isinstance(exc, (ValueError, KeyError, TypeError)) else 500
                payload = canonical(dict(error=type(exc).__name__,
                                         write_outcome='unknown-do-not-retry-blindly')).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Handler


def verified_snapshot(run):
    """Recheck existing R6 provenance offline; never download or reconvert."""
    from validation.accept_minilm_embedding import select_files, verify_file
    receipt = json.loads(personal_path(run/'download.json').read_text(encoding='utf-8'))
    info = json.loads(personal_path(run/'source-api.json').read_text(encoding='utf-8'))
    selected = select_files(info)
    if receipt['files'] != selected or receipt['revision'] != REVISION:
        raise ValueError('R6 source receipt mismatch')
    snapshot = personal_path(Path('/home/nclab/Yizhen/models/all-MiniLM-L6-v2')/REVISION)
    for name, entry in selected.items():
        if verify_file(personal_path(snapshot/name), entry) != receipt['sha256'][name]:
            raise ValueError('R6 snapshot changed')
    conversion = json.loads(personal_path(run/'conversion.json').read_text(encoding='utf-8'))
    derived = personal_path(snapshot/'model.safetensors')
    if (conversion['source_sha256'] != receipt['sha256']['pytorch_model.bin'] or
            conversion['derived_sha256'] != '53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db' or
            conversion['weights_only'] is not True or conversion['map_location'] != 'cpu' or
            conversion['tensor_count'] != 104):
        raise ValueError('R6 conversion receipt mismatch')
    verify_file(derived, dict(size=derived.stat().st_size, algorithm='sha256',
                             digest=conversion['derived_sha256']))
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--query-schema', required=True)
    parser.add_argument('--port', type=int, default=18082)
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--writable', action='store_true')
    args = parser.parse_args()
    if (sys.platform != 'linux' or platform.machine() != 'aarch64' or
            Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312')):
        raise RuntimeError('Dedicated Spark memory environment required')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    database = personal_path(args.database)
    if not run.is_dir() or not 1 <= args.port <= 65535:
        raise ValueError('Existing isolated run and valid port required')
    # Also enforce offline/personal caches when launched directly, before ML imports.
    for key in ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'HF_ASSETS_CACHE',
                'TRANSFORMERS_CACHE', 'TORCH_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'TMP', 'TEMP'):
        target = personal_path(run/key.lower())
        target.mkdir(exist_ok=True)
        os.environ[key] = str(target)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      CUDA_VISIBLE_DEVICES='', TOKENIZERS_PARALLELISM='false',
                      OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    import importlib.metadata
    from validation.plan_minilm_runtime import name_key
    baseline = json.loads(personal_path(Path('/home/nclab/Yizhen/runs/M20-R5-minilm-runtime-jhL8nq/runtime.json')).read_text())
    current = {name_key(d.metadata['Name']): d.version for d in importlib.metadata.distributions()}
    if baseline['status'] != 'PASS' or current != baseline['packages']:
        raise ValueError('Environment differs from R5')
    snapshot = verified_snapshot(personal_path(Path('/home/nclab/Yizhen/runs/M20-R6-minilm-acceptance-tNg6E3')))
    expected = manifest(args.query_schema)
    server = HTTPServer(('127.0.0.1', args.port), BaseHTTPRequestHandler)
    store = None
    try:
        import torch
        if torch.version.cuda is not None:
            raise ValueError('CPU torch required')
        torch.set_num_threads(1)
        from validation.serve_local_embedding import load_encoder
        from llm_controller.chroma_memory import ChromaMemoryStore
        from llm_controller.local_memory import LocalMemory
        encode = load_encoder(snapshot, expected)
        class Encoder:
            manifest = expected
        encoder = Encoder()
        encoder.encode = encode
        store = ChromaMemoryStore(database, expected, create=args.create, writable=args.writable)
        server.RequestHandlerClass = make_handler(expected, LocalMemory(store, encoder))
        (run/'ready.json').write_text(canonical(dict(manifest=expected, port=args.port,
                                                    writable=store.writable))+'\n', encoding='utf-8')
        print('M20-R7 memory ready: 127.0.0.1:{}'.format(args.port), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if store is not None:
            store.close()


if __name__ == '__main__':
    main()
