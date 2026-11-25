"""M21-R2 test-only lifecycle of one owned Spark memory service child."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from llm_controller.local_memory import personal_path

ROOT = Path(__file__).resolve().parents[1]


def offline_env(folder):
    env = os.environ.copy()
    for key in ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'HF_ASSETS_CACHE',
                'TRANSFORMERS_CACHE', 'TORCH_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'TMP', 'TEMP'):
        target = personal_path(folder/key.lower())
        target.mkdir()
        env[key] = str(target)
    env.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               CUDA_VISIBLE_DEVICES='', TOKENIZERS_PARALLELISM='false',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return env


@contextmanager
def memory_service(folder, database, expected, port, create=False):
    folder = personal_path(folder)
    folder.mkdir()
    command = ['/home/nclab/Yizhen/envs/memory-chroma0415-py312/bin/python',
               str(ROOT/'validation/serve_local_memory.py'), '--run-dir', str(folder),
               '--database', str(personal_path(database)), '--query-schema', expected['query_schema'],
               '--port', str(port)]
    if create:
        command.append('--create')
    with (folder/'service-console.txt').open('x', encoding='utf-8') as output:
        process = subprocess.Popen(command, env=offline_env(folder), stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+120
            while not (folder/'ready.json').exists():
                if process.poll() is not None:
                    raise RuntimeError('Owned memory child exited before ready')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Owned memory child readiness timeout')
                time.sleep(0.2)
            ready = json.loads((folder/'ready.json').read_text())
            if ready != dict(manifest=expected, port=port, writable=create):
                raise ValueError('Owned memory ready identity mismatch')
            yield
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Owned child PID {} did not stop; inspect manually'.format(process.pid))
            if code != 0:
                raise RuntimeError('Owned memory child exited nonzero: '+str(code))
