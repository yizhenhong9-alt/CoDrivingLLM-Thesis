"""M24 copy-only import of the reviewed 404-record seed0; no source DB open."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, personal_path
from llm_controller.memory_prompt import QUERY_SCHEMA
from validation.audit_vehicle_id_episode import audit
from validation.diagnose_memory_retrieval import inventory
from validation.memory_service_session import offline_env

SOURCE_COMMIT = '239a581efcdee9f311c7cb1c65794a94a856ec84'
SNAPSHOT = '43a5f971a61c551f962534351c93bf64c57ecf7a4497d232edd7b20f8d32ca28'
COUNT = 404
REFERENCE = ROOT/'modification_reports/M24-vehicle-id-naming/R3-seed0-audit.json'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_labels(step):
    require(step.get('vehicle_label_version') == 'M24-simulation-id', 'M24 labels required')
    rows = step['vehicle_identifiers']
    ids, names = [r['simulation_id'] for r in rows], [r['legacy_label'] for r in rows]
    require(len(ids) == len(set(ids)) and len(names) == len(set(names)), 'Duplicate identity/label')
    for row in rows:
        require(row['legacy_label'] in ('MDPVehicle #{}'.format(row['simulation_id']),
                                      'IDMVehicle #{}'.format(row['simulation_id'])), 'ID/label mismatch')
    controlled = [r['vehicle_id'] for r in step['submitted_vehicle_actions']]
    require(len(controlled) == 4 and len(set(controlled)) == 4 and set(controlled) <= set(ids),
            'Four registered CAV identities required')
    lookup = dict(zip(ids, names))
    require(all(lookup[i] == 'MDPVehicle #{}'.format(i) for i in controlled),
            'Controlled CAV identity must retain its MDPVehicle label')


def load_evidence(source):
    """Accept only the exact already-reviewed exported evidence, not an arbitrary pilot."""
    reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
    for name, expected in reference['source_sha256'].items():
        file = source/name
        file.resolve().relative_to(source.resolve())
        require(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == expected,
                'Reviewed evidence hash mismatch: '+name)
    result = audit(source)
    require(result['git_commit'] == SOURCE_COMMIT and result['steps'] == 101 and
            result['final_count'] == COUNT and result['final_snapshot'] == SNAPSHOT and
            result['test_only'] is True, 'Wrong retained seed0 boundary')
    manager = next((source/'live').glob('*/result.json'))
    ep_path = next((manager.parent/'traffic').glob('*/result.json'))
    episode = json.loads(ep_path.read_text(encoding='utf-8'))
    known = {}
    for name in episode['step_files']:
        step = json.loads((ep_path.parent/name).read_text(encoding='utf-8'))
        validate_labels(step)
        for event in step['memory_updates']:
            require(event['id'] not in known and event['metadata']['source']['test_only'] is True,
                    'Duplicate ID or changed pilot provenance')
            known[event['id']] = event
    require(len(known) == COUNT, 'Expected exactly 404 distinct records')
    return episode, known


def check_decision_sources():
    # A validation-only continuation commit is allowed; traffic/prompt/memory source changes are not.
    paths = ['highway_env', 'llm_controller', 'Run_multi_CAV_LLM.py',
             'validation/run_qwen_live_session.py', 'validation/memory_service_session.py',
             'validation/serve_local_memory.py', 'validation/serve_local_embedding.py',
             'validation/accept_memory_episode.py', 'validation/accept_memory_live_step.py']
    command = ['git', '-c', 'safe.directory='+ROOT.as_posix(), 'diff', '--exit-code',
               SOURCE_COMMIT, '--'] + paths
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    require(result.returncode == 0, 'Decision/model-service sources differ from retained seed0; stop')
    return dict(source_commit=SOURCE_COMMIT, unchanged_paths=paths)


def verify_copy(store, known):
    """Read all rows of COPY only. Never add, delete, update metadata, or re-embed."""
    require(len(known) == COUNT and store.count() == COUNT and store.snapshot_sha256() == SNAPSHOT,
            'Copy count/snapshot mismatch')
    data = store.collection.get(include=['documents', 'metadatas'])
    ids = data['ids']
    require(len(ids) == COUNT and len(set(ids)) == COUNT and set(ids) == set(known) and
            len(data['documents']) == len(data['metadatas']) == COUNT, 'Copy IDs/shape mismatch')
    for key, text, meta in zip(ids, data['documents'], data['metadatas']):
        require(text == known[key]['text'] and meta == {'codriving:metadata_json': canonical(known[key]['metadata'])},
                'Copy text/metadata mismatch')


def load_prepared(source, run):
    episode, known = load_evidence(source)
    receipt = json.loads((run/'retained-seed0.json').read_text(encoding='utf-8'))
    require(receipt['status'] == 'ready' and receipt['source'] == str(source) and
            receipt['source_unchanged'] is True and receipt['count'] == COUNT and
            receipt['snapshot'] == SNAPSHOT, 'Reviewed prepared 404-copy required')
    require(inventory(personal_path(source/'test-chroma')) == receipt['source_database_hashes'],
            'Original database changed since preparation')
    check_decision_sources()
    return episode, known, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312'),
            'Existing Spark memory environment required')
    source, run = personal_path(args.source), personal_path(args.run_dir)
    require(run.is_dir() and source != run and source not in run.parents and run not in source.parents and
            not (run/'experiment-chroma').exists() and not (run/'retained-seed0.json').exists(),
            'Fresh disjoint preparation target required; never retry over partial files')
    episode, known = load_evidence(source)
    fingerprints = check_decision_sources()
    original = personal_path(source/'test-chroma')
    require(original.is_dir() and not (original/'writer.lock').exists(),
            'Source absent or writer lock present; inspect, never remove locks automatically')
    before = inventory(original)
    require(bool(before), 'Empty source directory')
    receipt = dict(status='preparing', source=str(source), source_commit=SOURCE_COMMIT,
                   count=COUNT, snapshot=SNAPSHOT, source_database_hashes=before,
                   source_provenance='retained-verified-test-only-seed0', seed0_test_only=True,
                   later_seeds_test_only=False, decision_sources=fingerprints,
                   limitation='Exact file copy before opening; logical equality after reopen is not a claim about HNSW tie behavior.')
    try:
        clone = run/'experiment-chroma'
        shutil.copytree(str(original), str(clone))
        require(inventory(clone) == before, 'Physical copy hash mismatch')
        receipt['physical_copy_verified'] = True
        runtime = run/'preparation-runtime'
        runtime.mkdir()
        os.environ.update(offline_env(runtime))
        from llm_controller.chroma_memory import ChromaMemoryStore
        with ChromaMemoryStore(clone, manifest(QUERY_SCHEMA), writable=True) as store:
            verify_copy(store, known)
        # Copy precisely the reviewed evidence; no DB/cache copy into exported evidence.
        reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        for name in reference['source_sha256']:
            dest = run/'retained-seed0'/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(source/name), str(dest))
        receipt['status'] = 'ready'
    except BaseException as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['source_unchanged'] = inventory(original) == before
        if not receipt['source_unchanged']:
            receipt['status'] = 'failed-source-changed'
        (run/'retained-seed0.json').write_text(canonical(receipt)+'\n', encoding='utf-8')
    require(receipt['status'] == 'ready', 'Preparation failed; preserve all files')
    print('M24 copy READY: original unchanged; 404 records; seed0 retained; NO traffic started', flush=True)
    print('Prepared run directory: '+str(run), flush=True)


if __name__ == '__main__':
    main()
