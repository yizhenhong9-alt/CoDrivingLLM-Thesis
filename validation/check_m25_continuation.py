"""M25 import/continuation guards; all stores/processes are local stdlib doubles."""
import ast
from copy import deepcopy
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller import local_memory as lm
from validation import retain_m25_seed0 as retain
from validation.collect_memory_batch import selected_files
from validation.run_m25_memory_on_20seeds import main as batch_main


def sample():
    known = {'key-{}'.format(i): dict(text='text-'+str(i), metadata={
        'human_question':'None', 'negotiation_result':'None', 'final_action':'[1]',
        'comments':'safe', 'source':{'test_only':True}}) for i in range(396)}
    data = dict(ids=list(known), documents=[r['text'] for r in known.values()],
                metadatas=[{'codriving:metadata_json':lm.canonical(r['metadata'])} for r in known.values()])
    store = NS(count=lambda:396, snapshot_sha256=lambda:retain.SNAPSHOT,
               collection=NS(get=lambda **unused:deepcopy(data)))
    return known, data, store


class Tests(unittest.TestCase):
    def test_exact_396_copy_is_read_only_and_preserves_provenance(self):
        known, data, store = sample()
        before = deepcopy(data)
        retain.verify_copy(store, known)
        self.assertEqual(data, before)
        self.assertTrue(all(r['metadata']['source']['test_only'] for r in known.values()))

    def test_reject_wrong_count_snapshot_ids_text_metadata_shape(self):
        for kind in ('count','snapshot','id','duplicate','text','metadata','shape'):
            with self.subTest(kind=kind):
                known, data, store = sample()
                if kind=='count': store.count=lambda:395
                if kind=='snapshot': store.snapshot_sha256=lambda:'wrong'
                if kind=='id': data['ids'][0]='unknown'
                if kind=='duplicate': data['ids'][0]=data['ids'][1]
                if kind=='text': data['documents'][0]='changed'
                if kind=='metadata': data['metadatas'][0]={'codriving:metadata_json':'{}'}
                if kind=='shape': data['documents'].pop()
                with self.assertRaises(ValueError): retain.verify_copy(store, known)

    def test_evidence_tamper_rejected_before_audit_or_db(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ref=root/'reference.json'
            ref.write_text(json.dumps({'source_sha256':{'result.json':'expected'}}))
            (root/'result.json').write_text('changed')
            with patch.object(retain,'REFERENCE',ref), patch.object(retain,'audit') as audit:
                with self.assertRaisesRegex(ValueError,'hash mismatch'): retain.load_evidence(root)
                audit.assert_not_called()

    def test_prepared_receipt_and_source_mutation_guard(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(lm,'OWNER',Path(temp)):
            source,run=Path(temp)/'source',Path(temp)/'run'
            source.mkdir(); run.mkdir()
            receipt=dict(status='ready',source=str(source),source_unchanged=True,count=396,
                         snapshot=retain.SNAPSHOT,source_database_hashes={'sqlite':'hash'})
            for kind in ('good','snapshot','source','changed','failed'):
                value=deepcopy(receipt)
                if kind=='snapshot': value['snapshot']='wrong'
                if kind=='source': value['source']='other'
                if kind=='failed': value['status']='failed'
                (run/'retained-seed0.json').write_text(json.dumps(value))
                with patch.object(retain,'load_evidence',return_value=({},{})), \
                     patch.object(retain,'check_decision_sources',return_value={}), \
                     patch.object(retain,'inventory',return_value={} if kind=='changed' else {'sqlite':'hash'}):
                    if kind=='good': retain.load_prepared(source,run)
                    else:
                        with self.assertRaises(ValueError): retain.load_prepared(source,run)

    def test_preparation_never_opens_source_store(self):
        known,data,store=sample()
        with tempfile.TemporaryDirectory() as temp, patch.object(lm,'OWNER',Path(temp)), patch.dict(os.environ):
            root=Path(temp); source=root/'source'; run=root/'target'
            source.mkdir(); run.mkdir(); (source/'test-chroma').mkdir()
            (source/'test-chroma'/'db.sqlite3').write_bytes(b'immutable source')
            (source/'evidence.json').write_text('{}')
            ref=root/'reference.json'; ref.write_text(json.dumps({'source_sha256':{'evidence.json':'not-used'}}))
            before=retain.inventory(source/'test-chroma')
            with patch.object(retain,'REFERENCE',ref), patch.object(retain,'load_evidence',return_value=({},known)), \
                 patch.object(retain,'check_decision_sources',return_value={}), \
                 patch.object(sys,'platform','linux'), patch.object(retain.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/memory-chroma0415-py312'), \
                 patch.object(sys,'argv',['prepare','--source',str(source),'--run-dir',str(run)]), \
                 patch('llm_controller.chroma_memory.ChromaMemoryStore',return_value=nullcontext(store)) as factory:
                retain.main()
            self.assertEqual(factory.call_args.args[0],run/'experiment-chroma')
            self.assertEqual(retain.inventory(source/'test-chroma'),before)
            receipt=json.loads((run/'retained-seed0.json').read_text())
            self.assertEqual(receipt['status'],'ready')
            self.assertTrue(receipt['physical_copy_verified'] and receipt['source_unchanged'])
            self.assertEqual((run/'experiment-chroma'/'db.sqlite3').read_bytes(),b'immutable source')

    def test_runtime_source_change_blocks_preparation(self):
        with patch.object(retain.subprocess,'run',return_value=NS(returncode=1)):
            with self.assertRaisesRegex(ValueError,'sources differ'): retain.check_decision_sources()

    def test_mixed_pilot_and_formal_corpus_allowed_without_rewriting_pilot(self):
        # The original rolling-corpus validator checks new rows, not rewriting initial records.
        from validation.check_memory_episode import terminal_sample
        from validation.accept_memory_episode import validate_episode
        outer,ep,steps=terminal_sample(); ep['seed']=1
        old=deepcopy(steps[0]['memory_updates'][0]); old['id']='pilot'
        old['metadata']['source']['test_only']=True
        known={old['id']:old}
        ep['memory_session'].update(initial_count=1,final_count=5)
        for i,(q,e) in enumerate(zip(steps[0]['memory_queries'],steps[0]['memory_updates'])):
            q.update(corpus_count=i+1,candidate_count=min(i+1,2),candidates=[dict(
                id=r['id'],text=r['text'],metadata=deepcopy(r['metadata'])) for r in list(known.values())[:2]])
            e.update(count_before=i+1,count_after=i+2)
            e['metadata']['source']['test_only']=False
            e['write_receipt']['metadata_sha256']=lm.text_hash(lm.canonical(e['metadata']))
            known[e['id']]=e
        validate_episode(outer,ep,steps,expected_seed=1,initial_records={'pilot':old},test_only=False)
        self.assertIs(old['metadata']['source']['test_only'],True)

    def test_labels_and_mutually_exclusive_source_modes(self):
        step=dict(vehicle_label_version='M25-modulo1000-unique', vehicle_identifiers=[
            {'simulation_id':i,'legacy_label':'MDPVehicle #'+str(i)} for i in range(3,7)],
            submitted_vehicle_actions=[{'vehicle_id':i} for i in range(3,7)])
        retain.validate_labels(step)
        step['vehicle_identifiers'][1]['legacy_label']='MDPVehicle #3'
        with self.assertRaises(ValueError): retain.validate_labels(step)
        with patch.object(sys,'argv',['batch','--run-dir','/unused','--recovery-source','/old',
                                      '--retained-m25-source','/new']):
            with self.assertRaises(SystemExit) as error: batch_main()
        self.assertEqual(error.exception.code,2)

    def test_retained_evidence_export_excludes_databases_and_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            good=['retained-seed0.json','retained-seed0/acceptance.json',
                  'retained-seed0/live/m/result.json',
                  'retained-seed0/live/m/traffic/e/step-0000.json']
            bad=['retained-seed0/test-chroma/chroma.sqlite3','experiment-chroma/result.json',
                 'retained-seed0/live/m/cache/result.json','preparation-runtime/hf_home/config.json']
            for name in good+bad:
                file=root/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_text('{}')
            self.assertEqual({p.relative_to(root).as_posix() for p in selected_files(root)},set(good))
            # Every pinned reviewed evidence file must survive the retained pilot export.
            pinned=json.loads(retain.REFERENCE.read_text(encoding='utf-8'))['source_sha256']
            for name in pinned:
                file=root/'retained-seed0'/name
                file.parent.mkdir(parents=True,exist_ok=True); file.write_text('{}')
            exported={p.relative_to(root).as_posix() for p in selected_files(root)}
            self.assertTrue({'retained-seed0/'+name for name in pinned} <= exported)

    def test_python38_syntax(self):
        for name in ('retain_m25_seed0.py','run_m25_memory_on_20seeds.py','collect_memory_batch.py',
                     'check_m25_continuation.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'),feature_version=(3,8))

    def test_first_seed_starts_at_396_and_failure_stops_without_retry(self):
        from validation import run_m25_memory_on_20seeds as batch
        known,unused,store=sample()
        closed=[]
        @contextmanager
        def service(*args,**kwargs):
            self.assertFalse(kwargs['create'])
            self.assertTrue(kwargs['writable'])
            try: yield
            finally: closed.append(True)
        managers=[]
        def process(command,**kwargs):
            if command[0]=='git':
                return NS(returncode=0,stdout='continuation-commit\n' if 'rev-parse' in command else '')
            managers.append(command)
            self.assertEqual(command[command.index('--seed')+1],'1')
            return NS(returncode=1)
        with tempfile.TemporaryDirectory() as temp, patch.object(lm,'OWNER',Path(temp)):
            root=Path(temp); run=root/'run'; run.mkdir(); source=root/'source'; source.mkdir()
            repo=root/'repo'; (repo/'validation').mkdir(parents=True)
            baseline=json.loads((ROOT/'validation/memory_on_baseline_contract.json').read_text())
            (repo/'validation/memory_on_baseline_contract.json').write_text(json.dumps(baseline))
            ep=dict(config=baseline['config'],model=baseline['model'],parser_mode=baseline['parser'])
            receipt=dict(snapshot=retain.SNAPSHOT,source_commit=retain.SOURCE_COMMIT)
            with patch.object(batch,'ROOT',repo), patch.object(sys,'platform','linux'), \
                 patch.object(sys,'version_info',(3,8,20,'final',0)), \
                 patch.object(batch.platform,'machine',return_value='aarch64'), \
                 patch.object(sys,'prefix','/home/nclab/Yizhen/envs/codriving-sim-py38'), \
                 patch.object(sys,'argv',['batch','--run-dir',str(run),'--retained-m25-source',str(source)]), \
                 patch.object(batch.subprocess,'run',side_effect=process), \
                 patch.object(retain,'load_prepared',return_value=(ep,known,receipt)), \
                 patch.object(batch,'memory_service',service), \
                 patch.object(batch,'MemoryHTTPClient',return_value=NS(status=lambda:dict(count=396,snapshot_sha256=retain.SNAPSHOT))):
                with self.assertRaisesRegex(ValueError,'Seed 1 failed'): batch.main()
            result=json.loads((run/'batch-result.json').read_text())
            self.assertEqual(result['status'],'stopped_requires_review')
            self.assertEqual(result['resumed_seeds'],list(range(1,20)))
            self.assertEqual(len(result['episodes']),2)
            self.assertEqual(result['episodes'][1]['initial_count'],396)
            self.assertEqual(result['episodes'][1]['initial_snapshot_sha256'],retain.SNAPSHOT)
            self.assertEqual(len(managers),1)
            self.assertEqual(closed,[True])


if __name__=='__main__':
    unittest.main(verbosity=2)
