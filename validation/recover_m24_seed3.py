"""Direction 1: exact reviewed M24 860->800 COPY recovery, unchanged strict prompt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from llm_controller.local_memory import canonical, manifest, personal_path
from llm_controller.memory_prompt import QUERY_SCHEMA
from validation.audit_m24_stopped_batch import audit
from validation.diagnose_memory_retrieval import inventory
from validation.memory_service_session import offline_env
from validation.retain_m24_seed0 import check_decision_sources, load_evidence as load_pilot
from validation.collect_memory_batch import selected_files

CONTRACT=ROOT/'modification_reports/M24-vehicle-id-naming/R7-seed3-retry-source-contract.json'
BEFORE='c87691df4faa150eede66d0fde4b30a7b5e28fc6d7ca74a58e3ea3b8f88f3c94'
AFTER='e3b4429eef5e0508784dee80821bed5d8996824ecbd1aa5f243210faac34c787'


def require(ok,message):
    if not ok:
        raise ValueError(message)


def load_evidence(source):
    contract=json.loads(CONTRACT.read_text(encoding='utf-8'))
    for name,expected in contract['source_files_sha256'].items():
        file=(source/name).resolve()
        file.relative_to(source.resolve())
        require(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest()==expected,
                'Reviewed batch evidence mismatch: '+name)
    result=audit(source,verify_export=False)  # Source run lacks the collector-only manifest.
    require(result['final_count']==860 and result['retained_boundary_count']==800 and
            result['retained_boundary_snapshot']==AFTER and result['failed_final_snapshot']==BEFORE,
            'Wrong reviewed recovery boundary')
    batch=json.loads((source/'batch-result.json').read_text(encoding='utf-8'))
    require(batch['git_commit']==contract['source_commit'],'Wrong original attempt commit')
    unused,known=load_pilot(source/'retained-seed0')
    excluded={}
    for seed in (1,2,3):
        ep_path=next((source/('seed-{:02d}'.format(seed))/'live').glob('*/traffic/*/result.json'))
        ep=json.loads(ep_path.read_text(encoding='utf-8'))
        for name in ep['step_files']:
            step=json.loads((ep_path.parent/name).read_text(encoding='utf-8'))
            for event in step.get('memory_updates',[]):
                target=excluded if seed==3 else known
                require(event['id'] not in known and event['id'] not in excluded,'Duplicate memory ID')
                target[event['id']]=event
    require(len(known)==800 and len(excluded)==60 and set(excluded)==set(result['partial_ids']) and
            not set(known).intersection(excluded),'Exact 800 retained / 60 excluded IDs required')
    return batch,known,excluded


def verify_rows(store,expected,snapshot):
    require(store.count()==len(expected) and store.snapshot_sha256()==snapshot,'Copy count/snapshot mismatch')
    data=store.collection.get(include=['documents','metadatas'])
    ids=data['ids']
    require(len(ids)==len(expected) and len(set(ids))==len(ids) and set(ids)==set(expected) and
            len(data['documents'])==len(data['metadatas'])==len(ids),'Copy ID/shape mismatch')
    for key,text,metadata in zip(ids,data['documents'],data['metadatas']):
        require(text==expected[key]['text'] and metadata=={
            'codriving:metadata_json':canonical(expected[key]['metadata'])},'Copy text/metadata mismatch')


def restore_copy(store,retained,excluded,*,before=BEFORE,after=AFTER):
    require(store.writable and not set(retained).intersection(excluded),'Writable disjoint copy required')
    verify_rows(store,dict(retained,**excluded),before)
    # Only the independently verified COPY is passed here. Never rewrite metadata or add/re-embed.
    store.collection.delete(ids=sorted(excluded))
    verify_rows(store,retained,after)


def load_prepared(source,run):
    batch,known,excluded=load_evidence(source)
    receipt=json.loads((run/'seed3-recovery.json').read_text(encoding='utf-8'))
    require(receipt['status']=='ready' and receipt['source']==str(source) and
            receipt['source_unchanged'] is True and receipt['restored_count']==800 and
            receipt['restored_snapshot']==AFTER and set(receipt['excluded_ids'])==set(excluded) and
            receipt['prompt_changed'] is False and receipt['strict_changed'] is False,
            'Prepared exact 800-copy receipt required')
    require(inventory(personal_path(source/'experiment-chroma'))==receipt['source_database_hashes'],
            'Original 860 database changed since preparation')
    check_decision_sources()
    return batch,known,receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    require(sys.platform=='linux' and platform.machine()=='aarch64' and
            Path(sys.prefix)==Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312'),
            'Existing Spark memory environment required')
    source,run=personal_path(args.source),personal_path(args.run_dir)
    require(run.is_dir() and source!=run and source not in run.parents and run not in source.parents and
            not (run/'experiment-chroma').exists() and not (run/'seed3-recovery.json').exists(),
            'Fresh disjoint target required; retain partial failures, do not retry in place')
    batch,known,excluded=load_evidence(source)
    fingerprints=check_decision_sources()
    original=personal_path(source/'experiment-chroma')
    require(original.is_dir() and not (original/'writer.lock').exists(),
            'Original absent or writer lock present; inspect, never remove locks automatically')
    hashes=inventory(original)
    require(bool(hashes),'Empty original database directory')
    receipt=dict(status='preparing',source=str(source),source_commit=batch['git_commit'],
        source_database_hashes=hashes,original_count=860,excluded_ids=sorted(excluded),
        expected_snapshot=AFTER,prompt_changed=False,strict_changed=False,
        decision_sources=fingerprints,scope='ONE seed3 retry only; no automatic seeds4-19',
        limitation='Logical snapshot recovery, not bit-identical HNSW restoration or a guarantee of identical decisions.')
    try:
        clone=run/'experiment-chroma'
        shutil.copytree(str(original),str(clone))
        require(inventory(clone)==hashes,'Physical copy mismatch')
        receipt['physical_copy_verified']=True
        runtime=run/'recovery-runtime'; runtime.mkdir()
        os.environ.update(offline_env(runtime))
        from llm_controller.chroma_memory import ChromaMemoryStore
        with ChromaMemoryStore(clone,manifest(QUERY_SCHEMA),writable=True) as store:
            restore_copy(store,known,excluded)
            receipt.update(restored_count=store.count(),restored_snapshot=store.snapshot_sha256())
        for file in selected_files(source):
            personal_path(file)
            target=run/'prior-attempt'/file.relative_to(source)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(str(file),str(target))
        receipt['status']='ready'
    except BaseException as error:
        receipt.update(status='failed',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        receipt['source_unchanged']=inventory(original)==hashes
        if not receipt['source_unchanged']: receipt['status']='failed-source-changed'
        (run/'seed3-recovery.json').write_text(canonical(receipt)+'\n',encoding='utf-8')
    require(receipt['status']=='ready','Recovery failed; preserve all results')
    print('M24 seed3 recovery READY: original 860 unchanged; copy 800; NO traffic started',flush=True)
    print('Prepared retry directory: '+str(run),flush=True)


if __name__=='__main__':
    main()
