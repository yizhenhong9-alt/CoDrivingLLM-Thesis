"""Recovery deletion scope and logical-boundary tests with in-memory Chroma double."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from llm_controller import local_memory as lm
from llm_controller.chroma_memory import ChromaMemoryStore
from validation.check_chroma_memory import FakeClient
from validation.check_local_memory import unit
from validation.recover_memory_batch import restore_copy
from validation.collect_memory_batch import selected_files


class Tests(unittest.TestCase):
    def test_only_failed_ids_removed_and_boundary_matches(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(lm,'OWNER',Path(temp)):
            fake=FakeClient()
            with ChromaMemoryStore(Path(temp)/'copy',lm.manifest('synthetic-v1'),create=True,
                                   _client_factory=lambda path:fake) as store:
                store.add('retained','text',{'source':{'episode':'seed0'}},unit())
                expected=store.snapshot_sha256()
                store.add('partial','other',{'source':{'episode':'failed-seed1'}},unit(1))
                before=store.snapshot_sha256()
                deleted=[]
                def delete(*,ids):
                    deleted.extend(ids)
                    for key in ids:
                        del fake.collection.rows[key]
                with patch.object(fake.collection,'delete',side_effect=delete,create=True):
                    with self.assertRaises(ValueError):
                        restore_copy(store,{'retained':{}},{'partial':{}},'wrong',expected)
                    self.assertEqual(deleted,[])
                    self.assertEqual(store.count(),2)
                    restore_copy(store,{'retained':{}},{'partial':{}},before,expected)
                self.assertEqual(deleted,['partial'])
                self.assertEqual(set(fake.collection.rows),{'retained'})
                self.assertEqual(store.snapshot_sha256(),expected)

    def test_unknown_ids_rejected_before_delete(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(lm,'OWNER',Path(temp)):
            fake=FakeClient()
            with ChromaMemoryStore(Path(temp)/'copy',lm.manifest('synthetic-v1'),create=True,
                                   _client_factory=lambda path:fake) as store:
                store.add('unexpected','text',{'source':{'run':'test'}},unit())
                snapshot=store.snapshot_sha256()
                with self.assertRaises(ValueError):
                    restore_copy(store,{}, {'expected':{}},snapshot,snapshot)
                self.assertEqual(store.count(),1)

    def test_export_prior_failed_evidence_and_exclude_prior_db(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            names=['recovery.json','prior-attempt/batch-result.json',
                   'prior-attempt/seed-01/live/m/traffic/e/step-0001.json',
                   'prior-attempt/experiment-chroma/chroma.sqlite3']
            for name in names:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('{}')
            self.assertEqual({p.relative_to(root).as_posix() for p in selected_files(root)},set(names[:-1]))

    def test_python38_syntax(self):
        for name in ('recover_memory_batch.py','run_memory_on_20seeds.py','memory_service_session.py',
                     'collect_memory_batch.py','check_memory_recovery.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'),feature_version=(3,8))


if __name__=='__main__':
    unittest.main()
