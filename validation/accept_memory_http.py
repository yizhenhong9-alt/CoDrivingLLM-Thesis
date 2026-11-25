"""M20-R7 Spark Python 3.8 client / Python 3.12 service acceptance, isolated DB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, personal_path
from llm_controller.memory_http import MemoryHTTPClient, MemoryServiceError


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18082)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            sys.version_info[:2] == (3, 8) and
            Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'),
            'Run only in existing Spark sim Python 3.8')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    require(run.is_dir(), 'Existing run directory required')
    expected = manifest('m20-r7-original-fixtures-v1')
    client = MemoryHTTPClient(expected, args.port)
    fixture_bytes = (ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_bytes()
    rows = json.loads(fixture_bytes)['rows']
    metadata = []
    for i, row in enumerate(rows):
        item = dict(row['would_write']['metadata'])
        item['source'] = dict(test_only=True, fixture_index=i,
                              fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest())
        metadata.append(item)
    snapshot = None
    phases = []
    for phase in ('create', 'reopen'):
        phase_dir = personal_path(run/phase)
        phase_dir.mkdir()
        env = os.environ.copy()
        for key in ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'HF_ASSETS_CACHE',
                    'TRANSFORMERS_CACHE', 'TORCH_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'TMP', 'TEMP'):
            target = personal_path(phase_dir/key.lower())
            target.mkdir()
            env[key] = str(target)
        env.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   CUDA_VISIBLE_DEVICES='', TOKENIZERS_PARALLELISM='false',
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        command = ['/home/nclab/Yizhen/envs/memory-chroma0415-py312/bin/python',
                   str(ROOT/'validation/serve_local_memory.py'), '--run-dir', str(phase_dir),
                   '--database', str(run/'test-chroma'), '--query-schema', expected['query_schema'],
                   '--port', str(args.port)]
        if phase == 'create':
            command.append('--create')
        with (phase_dir/'service-console.txt').open('x', encoding='utf-8') as output:
            process = subprocess.Popen(command, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+120
                while not (phase_dir/'ready.json').exists():
                    require(process.poll() is None, 'Service exited before ready; inspect service-console')
                    require(time.monotonic() < deadline, 'Service readiness timeout')
                    time.sleep(0.2)
                ready = json.loads((phase_dir/'ready.json').read_text())
                require(ready['manifest'] == expected and ready['port'] == args.port, 'Ready mismatch')
                if phase == 'create':
                    require(client.retrieve(rows[0]['query']) == [], 'New test DB not empty')
                    for i, row in enumerate(rows):
                        client.add('fixture-'+str(i), row['would_write']['page_content'], metadata[i])
                    try:
                        client.add('fixture-0', rows[0]['would_write']['page_content'], metadata[0])
                    except MemoryServiceError:
                        pass
                    else:
                        raise ValueError('Duplicate ID accepted')
                else:
                    try:
                        client.add('readonly-probe', rows[0]['would_write']['page_content'], metadata[0])
                    except MemoryServiceError:
                        pass
                    else:
                        raise ValueError('Readonly add accepted')
                for i, row in enumerate(rows):
                    hits = client.retrieve(row['query'])
                    require(len(hits) == 2 and hits[0]['id'] == 'fixture-'+str(i), 'Top-2/top-1 mismatch')
                    for hit in hits:
                        index = int(hit['id'].split('-')[1])
                        require(hit['metadata'] == metadata[index] and
                                hit['text'] == rows[index]['would_write']['page_content'], 'Original metadata/text mismatch')
                status = client.status()
                require(status['writable'] == (phase == 'create'), 'Writable mode mismatch')
                if snapshot is None:
                    snapshot = status['snapshot_sha256']
                require(snapshot == status['snapshot_sha256'], 'Cross-process corpus changed')
                require(not any(name in sys.modules for name in ('torch', 'chromadb', 'transformers')),
                        'ML dependency imported in sim client')
                phases.append(dict(phase=phase, status='PASS', snapshot_sha256=snapshot))
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                try:
                    code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    raise RuntimeError('Own memory child did not stop; inspect PID {}'.format(process.pid))
                require(code == 0, 'Memory child exit nonzero: '+str(code))
    result = dict(status='PASS', client_python=sys.version, phases=phases,
                  limitation='Two test-only original templates; no traffic semantics/safety or production memory-on validation.')
    (run/'acceptance.json').write_text(canonical(result)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
