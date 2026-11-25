"""M20 Spark-only CPU embedding server; never download weights or start Qwen."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import (REVISION, canonical, manifest, personal_path,
                                         texts_checked, text_hash, vector)


def make_handler(expected, encode):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass  # Do not log scenario text.

        def do_POST(self):
            try:
                if self.path != '/embed':
                    raise ValueError('Unknown endpoint')
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('Transfer-Encoding unsupported')
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError('One Content-Length required')
                length = int(lengths[0])
                if not 0 < length <= 1024*1024:
                    raise ValueError('Invalid request size')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete request')
                request = json.loads(raw.decode('utf-8'))
                if request.get('manifest') != expected:
                    raise ValueError('Request manifest mismatch')
                texts = texts_checked(request.get('texts'))
                vectors = encode(texts)
                if len(vectors) != len(texts):
                    raise ValueError('Encoder count mismatch')
                body = dict(manifest=expected, data=[
                    dict(index=i, text_sha256=text_hash(text),
                         embedding=vector(v, expected['dimension']))
                    for i, (text, v) in enumerate(zip(texts, vectors))])
                status = 200
            except Exception as exc:
                body, status = dict(error=type(exc).__name__), 400
            payload = canonical(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Handler


def load_encoder(snapshot, expected):
    """Only called by explicit Spark main; imports do not load any model."""
    import torch
    from transformers import AutoModel, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True,
                                              trust_remote_code=False)
    model = AutoModel.from_pretrained(str(snapshot), local_files_only=True,
                                      trust_remote_code=False, use_safetensors=True).to('cpu').eval()
    if model.config.hidden_size != expected['dimension']:
        raise ValueError('Unexpected hidden dimension')

    def encode(texts):
        # Check before inference: never silently truncate long situation text.
        tokens = tokenizer(texts, padding=False, truncation=False)
        if any(len(ids) > expected['max_tokens'] for ids in tokens['input_ids']):
            raise ValueError('Embedding input exceeds 256 tokens')
        tokens = tokenizer(texts, padding=True, truncation=False, return_tensors='pt')
        with torch.inference_mode():
            hidden = model(**tokens).last_hidden_state
            mask = tokens['attention_mask'].unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden*mask).sum(1)/mask.sum(1).clamp(min=1e-9)
            return torch.nn.functional.normalize(pooled, p=2, dim=1).tolist()
    return encode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True,
                        help='Previously verified local HF snapshot, directory name must be revision')
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--query-schema', required=True)
    parser.add_argument('--port', type=int, default=18081)
    args = parser.parse_args(argv)
    if sys.platform != 'linux':
        raise RuntimeError('Only run manually on Spark Linux')
    personal_path(ROOT)
    snapshot = personal_path(args.snapshot)
    runtime = personal_path(args.runtime_dir)
    if snapshot.name != REVISION or not snapshot.is_dir():
        raise ValueError('Expected pinned snapshot directory')
    if not 1 <= args.port <= 65535:
        raise ValueError('Invalid port')
    # Reject snapshots whose symlinked model blobs escape the personal root.
    files = sorted(p for p in snapshot.rglob('*') if p.is_file())
    if not files:
        raise ValueError('Empty snapshot')
    hashes = {}
    for file in files:
        personal_path(file)
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
        hashes[file.relative_to(snapshot).as_posix()] = digest.hexdigest()
    runtime.mkdir(parents=True, exist_ok=False)
    for key, child in (('HF_HOME', 'hf'), ('HF_HUB_CACHE', 'hub'),
                       ('HUGGINGFACE_HUB_CACHE', 'hub-legacy'),
                       ('HF_ASSETS_CACHE', 'assets'), ('TRANSFORMERS_CACHE', 'transformers'),
                       ('TORCH_HOME', 'torch'), ('XDG_CACHE_HOME', 'cache'),
                       ('TMPDIR', 'tmp'), ('TMP', 'tmp-windows'), ('TEMP', 'temp')):
        path = personal_path(runtime/child)
        path.mkdir()
        os.environ[key] = str(path)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      CUDA_VISIBLE_DEVICES='', TOKENIZERS_PARALLELISM='false')
    expected = manifest(args.query_schema)
    # Bind first, so an occupied port fails before loading the encoder.
    server = HTTPServer(('127.0.0.1', args.port), make_handler(expected, lambda texts: []))
    try:
        encode = load_encoder(snapshot, expected)
        import importlib.metadata
        receipt = dict(manifest=expected, snapshot=str(snapshot), source_sha256=hashes,
                       device='cpu', python=sys.version,
                       packages={name: importlib.metadata.version(name)
                                 for name in ('torch', 'transformers', 'tokenizers', 'safetensors')})
        (runtime/'runtime.json').write_text(canonical(receipt)+'\n', encoding='utf-8')
        server.RequestHandlerClass = make_handler(expected, encode)
        print('M20 embedding ready at 127.0.0.1:{}; CPU; no driving integration'.format(args.port), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
