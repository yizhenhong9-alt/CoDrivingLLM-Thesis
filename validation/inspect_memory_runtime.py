"""M20-R1 Spark read-only package preflight: no package/model imports or install."""
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys


def inspect():
    owner = Path('/home/nclab/Yizhen').resolve()
    root = Path(__file__).resolve().parents[1]
    root.relative_to(owner)
    # The venv executable may legitimately resolve to a base Python outside owner.
    Path(sys.prefix).resolve().relative_to(owner)
    packages = {}
    for name in ('chromadb', 'numpy', 'pydantic', 'chroma-hnswlib', 'posthog',
                 'langchain', 'torch', 'transformers', 'tokenizers', 'safetensors'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    blockers = []
    if packages['chromadb'] != '0.4.15':
        blockers.append('Need chromadb==0.4.15 for this backend; do not upgrade existing environments automatically')
    if sqlite3.sqlite_version_info < (3, 35, 0):
        blockers.append('Chroma 0.4.15 requires SQLite >= 3.35.0')
    return dict(status='preflight_blocked' if blockers else 'ready_for_synthetic_chroma_test',
                python=sys.version, prefix=sys.prefix, executable=sys.executable,
                machine=platform.machine(), root=str(root), sqlite=sqlite3.sqlite_version,
                packages=packages, blockers=blockers, model_loaded=False,
                limitation='Package metadata only; imports/ABI/ARM64 and true embedding are unverified')


if __name__ == '__main__':
    if sys.platform != 'linux':
        raise RuntimeError('Run manually on Spark Linux')
    print(json.dumps(inspect(), ensure_ascii=False, indent=2))
