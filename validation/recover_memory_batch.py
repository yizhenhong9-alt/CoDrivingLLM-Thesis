"""M23-R3 restore a new copy to the verified seed0 boundary; source DB never opened."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from llm_controller.local_memory import canonical, personal_path
from validation.diagnose_memory_retrieval import inventory
from validation.collect_memory_batch import selected_files
from validation.memory_service_session import offline_env
from validation.accept_memory_episode import validate_episode


def require(ok,message):
    if not ok:
        raise ValueError(message)


def load_evidence(source):
    batch=json.loads((source/'batch-result.json').read_text(encoding='utf-8'))
    require(batch['git_commit']=='efc8a01d0196c90a77424e47952a3c10a3f94002' and
            batch['status']=='stopped_requires_review' and len(batch['episodes'])==2,
            'Only the reviewed original failed batch is supported')
    first,failed=batch['episodes']
    require(first['seed']==0 and first['status']=='verified' and first['final_count']==396 and
            failed['seed']==1 and failed['manager_exit_code']==1,'Unexpected recovery boundary')
    load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    def episode_for(seed):
        managers=list((source/('seed-{:02d}'.format(seed))/'live').glob('*/result.json'))
        require(len(managers)==1,'Exactly one original attempt required')
        outer=load(managers[0])
        ep_path=personal_path(Path(outer['traffic_report']))
        ep_path.relative_to(source)
        episode=load(ep_path)
        steps=[load(personal_path(ep_path.parent/name)) for name in episode['step_files']]
        return outer,episode,steps
    outer,ep,steps=episode_for(0)
    validate_episode(outer,ep,steps,expected_seed=0,test_only=False)
    retained={e['id']:e for step in steps for e in step['memory_updates']}
    bad_outer,bad_ep,bad_steps=episode_for(1)
    removed={e['id']:e for step in bad_steps for e in step.get('memory_updates',[]) if e['status']=='verified'}
    require(len(retained)==396 and len(removed)==5 and not set(retained)&set(removed), 'Unexpected write set')
    require(bad_ep['actual_environment_steps']==1 and bad_ep['memory_session']['final_count']==401 and
            bad_ep['memory_session']['final_snapshot_verified'] is True and
            bad_ep['memory_session']['initial_snapshot_sha256']==first['final_snapshot_sha256'] and
            bad_outer['shutdown']['clean_observation'] is True,'Failed attempt does not match reviewed state')
    require(all(e['status']=='verified' for step in bad_steps for e in step.get('memory_updates',[])),
            'Uncertain write outcome; recovery blocked')
    return batch,retained,removed,bad_ep['memory_session']['final_snapshot_sha256']


def restore_copy(store,retained,removed,before_snapshot,after_snapshot):
    require(store.writable,'Recovery copy must hold its own writer lock')
    require(store.count()==len(retained)+len(removed) and store.snapshot_sha256()==before_snapshot,
            'Copy is not the reviewed 401-record state')
    ids=store.collection.get(include=['documents'])['ids']
    require(len(ids)==len(set(ids)) and set(ids)==set(retained)|set(removed),'Copy IDs differ from evidence')
    # Deliberate deletion ONLY in the newly created copy; original attempt remains immutable.
    store.collection.delete(ids=sorted(removed))
    require(store.count()==len(retained) and store.snapshot_sha256()==after_snapshot,
            'Restored copy does not exactly match verified seed0 logical snapshot')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    require(sys.platform=='linux' and platform.machine()=='aarch64' and
            Path(sys.prefix)==Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312'),'Existing Spark memory environment required')
    source,run=personal_path(args.source),personal_path(args.run_dir)
    require(source!=run and run.is_dir() and not (run/'experiment-chroma').exists(),'Fresh distinct recovery target required')
    batch,retained,removed,old_snapshot=load_evidence(source)
    original=personal_path(source/'experiment-chroma')
    require(not (original/'writer.lock').exists(),'Original writer active/stale lock: inspect; never remove automatically')
    original_hashes=inventory(original)
    receipt=dict(status='preparing',source=str(source),source_batch=batch,retained_seed=0,
        retained_count=396,excluded_failed_attempt_ids=sorted(removed),source_file_hashes=original_hashes,
        expected_snapshot=batch['episodes'][0]['final_snapshot_sha256'],
        limitation='Logical seed0 state restored, not a bit-identical HNSW index; repaired adapter and retry use a different commit.')
    try:
        clone=run/'experiment-chroma'
        shutil.copytree(str(original),str(clone))
        require(inventory(clone)==original_hashes,'Copy file hash mismatch')
        runtime=run/'recovery-runtime'
        runtime.mkdir()
        os.environ.update(offline_env(runtime))
        from llm_controller.chroma_memory import ChromaMemoryStore
        spec=json.loads((source/'memory-config.json').read_text())['manifest']
        with ChromaMemoryStore(clone,spec,writable=True) as store:
            restore_copy(store,retained,removed,old_snapshot,receipt['expected_snapshot'])
            receipt.update(restored_count=store.count(),restored_snapshot=store.snapshot_sha256())
        # Keep selected evidence of BOTH original seeds, including failed seed1.
        for path in selected_files(source):
            personal_path(path)
            relative=path.relative_to(source)
            target=run/'prior-attempt'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(str(path),str(target))
            if relative.parts[0]=='seed-00':
                retained_target=run/relative
                retained_target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(str(path),str(retained_target))
        receipt['status']='ready'
    except BaseException as error:
        receipt.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        receipt['source_unchanged']=inventory(original)==original_hashes
        if not receipt['source_unchanged']:
            receipt['status']='failed-source-changed'
        (run/'recovery.json').write_text(canonical(receipt)+'\n',encoding='utf-8')
    require(receipt['status']=='ready','Recovery failed; retain evidence')
    print('M23-R3 recovery READY; original unchanged; restored=396; seed0 will not rerun',flush=True)


if __name__=='__main__':
    main()
