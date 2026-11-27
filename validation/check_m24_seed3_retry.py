"""Direction1 scope/boundary regressions. No real Chroma/model/service imports at runtime."""
import ast
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from llm_controller import local_memory as lm
from validation import recover_m24_seed3 as recovery
from validation import run_m24_seed3_retry as retry
from validation.collect_memory_batch import selected_files


def sample():
    retained={'keep-{}'.format(i):dict(text='retained '+str(i),metadata={
        'source':{'test_only':i<404},'final_action':'[1]'}) for i in range(800)}
    excluded={'exclude-{}'.format(i):dict(text='partial '+str(i),metadata={
        'source':{'test_only':False},'final_action':'[3]'}) for i in range(60)}
    rows=deepcopy({**retained,**excluded}); deleted=[]
    def get(**unused):
        return dict(ids=list(rows),documents=[v['text'] for v in rows.values()],
            metadatas=[{'codriving:metadata_json':lm.canonical(v['metadata'])} for v in rows.values()])
    def delete(*,ids):
        deleted.extend(ids)
        for key in ids: del rows[key]
    store=NS(writable=True,count=lambda:len(rows),snapshot_sha256=lambda:
        recovery.BEFORE if set(rows)==set(retained)|set(excluded) else recovery.AFTER if set(rows)==set(retained) else 'bad',
        collection=NS(get=get,delete=delete))
    return retained,excluded,rows,deleted,store


class Tests(unittest.TestCase):
    def test_only_the_60_reviewed_ids_removed(self):
        kept,bad,rows,deleted,store=sample()
        before=deepcopy(kept)
        recovery.restore_copy(store,kept,bad)
        self.assertEqual(set(deleted),set(bad)); self.assertEqual(len(deleted),60)
        self.assertEqual(rows,before)
        self.assertEqual(store.count(),800)

    def test_bad_boundary_payload_and_unknown_ids_block_before_delete(self):
        for kind in ('snapshot','count','id','text','metadata','readonly','overlap','shape'):
            with self.subTest(kind=kind):
                kept,bad,rows,deleted,store=sample()
                if kind=='snapshot': store.snapshot_sha256=lambda:'wrong'
                if kind=='count': store.count=lambda:859
                if kind=='id': rows['unknown']=rows.pop('exclude-0')
                if kind=='text': rows['keep-0']['text']='changed'
                if kind=='metadata': rows['keep-0']['metadata']['source']['test_only']=False
                if kind=='readonly': store.writable=False
                if kind=='overlap': bad['keep-0']=kept['keep-0']
                if kind=='shape':
                    original=store.collection.get
                    store.collection.get=lambda **kw:dict(original(**kw),documents=[])
                with self.assertRaises(ValueError): recovery.restore_copy(store,kept,bad)
                self.assertEqual(deleted,[])

    def test_failed_post_delete_verification_is_not_success(self):
        kept,bad,rows,deleted,store=sample()
        store.collection.delete=lambda **kw:None
        with self.assertRaises(ValueError): recovery.restore_copy(store,kept,bad)
        self.assertEqual(len(rows),860)

    def test_changed_evidence_rejected_without_opening_store(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); ref=root/'ref.json'; (root/'evidence.json').write_text('changed')
            ref.write_text(json.dumps({'source_files_sha256':{'evidence.json':'wrong'}}))
            with patch.object(recovery,'CONTRACT',ref),patch.object(recovery,'audit') as audit:
                with self.assertRaisesRegex(ValueError,'evidence mismatch'): recovery.load_evidence(root)
                audit.assert_not_called()

    def test_prepare_opens_only_the_copy_and_preserves_original_bytes(self):
        kept,bad,rows,deleted,store=sample()
        with tempfile.TemporaryDirectory() as temp,patch.object(lm,'OWNER',Path(temp)),patch.dict(os.environ):
            root=Path(temp); source=root/'original'; source.mkdir(); run=root/'copy'; run.mkdir()
            db=source/'experiment-chroma'; db.mkdir(); (db/'chroma.sqlite3').write_bytes(b'original860')
            (source/'batch-result.json').write_text('{}')
            before=recovery.inventory(db)
            with patch.object(sys,'platform','linux'),patch.object(recovery.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/memory-chroma0415-py312'), \
                 patch.object(sys,'argv',['prepare','--source',str(source),'--run-dir',str(run)]), \
                 patch.object(recovery,'load_evidence',return_value=({'git_commit':'old'},kept,bad)), \
                 patch.object(recovery,'check_decision_sources',return_value={}), \
                 patch('llm_controller.chroma_memory.ChromaMemoryStore',return_value=nullcontext(store)) as factory:
                recovery.main()
            self.assertEqual(factory.call_args.args[0],run/'experiment-chroma')
            self.assertEqual(recovery.inventory(db),before)
            result=json.loads((run/'seed3-recovery.json').read_text())
            self.assertEqual(result['status'],'ready'); self.assertEqual(result['restored_count'],800)
            self.assertTrue(result['source_unchanged'] and result['physical_copy_verified'])
            self.assertEqual((db/'chroma.sqlite3').read_bytes(),b'original860')

    def test_active_or_stale_source_lock_is_never_removed(self):
        kept,bad,unused,deleted,store=sample()
        with tempfile.TemporaryDirectory() as temp,patch.object(lm,'OWNER',Path(temp)):
            root=Path(temp); source=root/'source'; source.mkdir(); run=root/'run'; run.mkdir()
            (source/'experiment-chroma').mkdir(); lock=source/'experiment-chroma/writer.lock'; lock.write_text('other writer')
            with patch.object(sys,'platform','linux'),patch.object(recovery.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/memory-chroma0415-py312'), \
                 patch.object(sys,'argv',['prepare','--source',str(source),'--run-dir',str(run)]), \
                 patch.object(recovery,'load_evidence',return_value=({'git_commit':'old'},kept,bad)), \
                 patch.object(recovery,'check_decision_sources',return_value={}):
                with self.assertRaisesRegex(ValueError,'writer lock'): recovery.main()
            self.assertEqual(lock.read_text(),'other writer')
            self.assertFalse((run/'experiment-chroma').exists())

    def test_receipt_snapshot_and_source_change_block_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(lm,'OWNER',Path(temp)):
            root=Path(temp); source=root/'source'; source.mkdir(); run=root/'run'; run.mkdir()
            receipt=dict(status='ready',source=str(source),source_unchanged=True,restored_count=800,
                restored_snapshot=recovery.AFTER,excluded_ids=['bad'],prompt_changed=False,strict_changed=False,
                source_database_hashes={'db':'hash'})
            for kind in ('good','snapshot','prompt','strict','source_changed'):
                value=deepcopy(receipt)
                if kind=='snapshot': value['restored_snapshot']='wrong'
                if kind=='prompt': value['prompt_changed']=True
                if kind=='strict': value['strict_changed']=True
                (run/'seed3-recovery.json').write_text(json.dumps(value))
                with patch.object(recovery,'load_evidence',return_value=({}, {}, {'bad':{}})), \
                     patch.object(recovery,'check_decision_sources',return_value={}), \
                     patch.object(recovery,'inventory',return_value={} if kind=='source_changed' else {'db':'hash'}):
                    if kind=='good': recovery.load_prepared(source,run)
                    else:
                        with self.assertRaises(ValueError): recovery.load_prepared(source,run)

    def test_one_seed3_failure_closes_service_and_cannot_run_again(self):
        closed=[]; commands=[]
        @contextmanager
        def service(*args,**kwargs):
            self.assertTrue(kwargs['writable'])
            try: yield
            finally: closed.append(True)
        def process(command,**kw):
            if command[0]=='git':
                return NS(returncode=0,stdout='new-commit' if 'rev-parse' in command else '')
            commands.append(command)
            self.assertEqual(command[command.index('--seed')+1],'3')
            return NS(returncode=1)
        with tempfile.TemporaryDirectory() as temp,patch.object(lm,'OWNER',Path(temp)):
            root=Path(temp); run=root/'run'; run.mkdir(); repo=root/'repo'; repo.mkdir()
            with patch.object(sys,'platform','linux'),patch.object(retry.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'version_info',(3,8,20,'final',0)), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/codriving-sim-py38'), \
                 patch.object(sys,'argv',['retry','--run-dir',str(run)]),patch.object(retry,'ROOT',repo), \
                 patch.object(retry,'personal_path',side_effect=lambda p:Path(p)), \
                 patch.object(retry,'load_prepared',return_value=({'git_commit':'old','baseline_contract':{}},{},{})), \
                 patch.object(retry.subprocess,'run',side_effect=process),patch.object(retry,'memory_service',service), \
                 patch.object(retry,'MemoryHTTPClient',return_value=NS(status=lambda:dict(count=800,snapshot_sha256=recovery.AFTER))):
                with self.assertRaisesRegex(ValueError,'retry failed'): retry.main()
                with self.assertRaisesRegex(ValueError,'Only one retry'): retry.main()
            result=json.loads((run/'retry-result.json').read_text())
            self.assertEqual(result['status'],'stopped_requires_review')
            self.assertEqual(result['attempt'],2); self.assertEqual(result['final_count'],800)
            self.assertEqual(len(commands),1); self.assertEqual(closed,[True])
            self.assertTrue((run/'retry-started.json').exists()); self.assertFalse((run/'seed-04').exists())

    def test_export_preserves_failure_and_excludes_databases(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            good=['seed3-recovery.json','retry-started.json','retry-result.json',
                  'prior-attempt/batch-result.json','prior-attempt/seed-03/live/m/traffic/e/step-0015.json']
            bad=['prior-attempt/experiment-chroma/chroma.sqlite3','experiment-chroma/result.json']
            for name in good+bad:
                file=root/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_text('{}')
            self.assertEqual({p.relative_to(root).as_posix() for p in selected_files(root)},set(good))

    def test_success_validates_warm_corpus_and_still_stops_after_seed3(self):
        from validation.check_memory_episode import terminal_sample
        outer,ep,steps=terminal_sample(); step=steps[0]
        kept,unused,unused_rows,unused_deleted,unused_store=sample()
        history={k:dict(v,id=k) for k,v in kept.items()}
        ep.update(seed=3,git_commit='new-commit',git_status='',model='fixed-model',parser_mode='strict',
                  config={'duration':50,'policy_frequency':5},settings={'max_steps':300,'wall_seconds':3600},
                  step_files=['step-0000.json'])
        ep['memory_session'].update(initial_count=800,final_count=804,initial_snapshot_sha256=recovery.AFTER)
        for i,(q,e) in enumerate(zip(step['memory_queries'],step['memory_updates'])):
            q.update(corpus_count=800+i,candidate_count=2,candidates=[dict(
                id=r['id'],text=r['text'],metadata=deepcopy(r['metadata'])) for r in list(history.values())[:2]])
            e.update(count_before=800+i,count_after=801+i)
            if i==0: q['snapshot_sha256']=e['snapshot_before']=recovery.AFTER
            e['metadata']['source']['test_only']=False
            e['write_receipt']['metadata_sha256']=lm.text_hash(lm.canonical(e['metadata']))
            history[e['id']]=e
        step.update(vehicle_label_version='M24-simulation-id',
            vehicle_identifiers=[{'simulation_id':i,'legacy_label':'MDPVehicle #'+str(i)} for i in range(3,7)],
            submitted_vehicle_actions=[{'vehicle_id':i} for i in range(3,7)],
            final_vehicles=[{'vehicle_id':i,'crashed':False} for i in range(3,7)],
            info={'cav_crashed':False,'agents_dones':[True]*4},step_observation={'simulated_seconds':0.2})
        state={'count':800,'snapshot_sha256':recovery.AFTER}; commands=[]
        def process(command,**kw):
            if command[0]=='git': return NS(returncode=0,stdout='new-commit' if 'rev-parse' in command else '')
            commands.append(command)
            manager=Path(command[command.index('--output-dir')+1])/'manager'
            traffic=manager/'traffic/episode'; traffic.mkdir(parents=True)
            ep_path=traffic/'result.json'
            outer.update(git_commit='new-commit',traffic_report=str(ep_path))
            (manager/'result.json').write_text(json.dumps(outer))
            ep_path.write_text(json.dumps(ep)); (traffic/'step-0000.json').write_text(json.dumps(step))
            state.update(count=804,snapshot_sha256=ep['memory_session']['final_snapshot_sha256'])
            return NS(returncode=0)
        with tempfile.TemporaryDirectory() as temp,patch.object(lm,'OWNER',Path(temp)):
            root=Path(temp); run=root/'run'; run.mkdir(); repo=root/'repo'; repo.mkdir()
            baseline=dict(config=ep['config'],model=ep['model'],parser='strict')
            with patch.object(sys,'platform','linux'),patch.object(retry.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'version_info',(3,8,20,'final',0)), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/codriving-sim-py38'), \
                 patch.object(sys,'argv',['retry','--run-dir',str(run)]),patch.object(retry,'ROOT',repo), \
                 patch.object(retry,'personal_path',side_effect=lambda p:Path(p)), \
                 patch.object(retry,'load_prepared',return_value=({'git_commit':'old','baseline_contract':baseline},kept,{})), \
                 patch.object(retry.subprocess,'run',side_effect=process), \
                 patch.object(retry,'memory_service',return_value=nullcontext()), \
                 patch.object(retry,'MemoryHTTPClient',return_value=NS(status=lambda:dict(state))):
                retry.main()
            result=json.loads((run/'retry-result.json').read_text())
            self.assertEqual(result['status'],'verified'); self.assertEqual(result['final_count'],804)
            self.assertTrue(result['memory_service_closed']); self.assertEqual(len(commands),1)
            self.assertFalse((run/'seed-04').exists())

    def test_python38_and_no_prompt_changes(self):
        for name in ('recover_m24_seed3.py','run_m24_seed3_retry.py','check_m24_seed3_retry.py',
                     'audit_m24_stopped_batch.py','collect_memory_batch.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'),feature_version=(3,8))
        source=(ROOT/'validation/run_m24_seed3_retry.py').read_text(encoding='utf-8')
        self.assertIn("'--seed','3'",source)
        self.assertNotIn('range(3,20)',source)


if __name__=='__main__':
    unittest.main(verbosity=2)
