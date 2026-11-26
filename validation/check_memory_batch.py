"""M23 shared-corpus validation and evidence-only exporter regression tests."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation.check_memory_episode import terminal_sample
from validation.accept_memory_episode import validate_episode
from validation.collect_memory_batch import selected_files
from llm_controller.local_memory import canonical, text_hash


class Tests(unittest.TestCase):
    def test_later_seed_shared_corpus(self):
        outer,episode,steps=terminal_sample()
        episode['seed']=1
        session=episode['memory_session']
        session.update(initial_count=1,final_count=5)
        old=deepcopy(steps[0]['memory_updates'][0])
        old['id']='previous-episode'
        old['metadata']['source']['test_only']=False
        known={old['id']:old}
        for i,(query,event) in enumerate(zip(steps[0]['memory_queries'],steps[0]['memory_updates'])):
            query.update(corpus_count=i+1,candidate_count=min(i+1,2),candidates=[dict(id=e['id'],text=e['text'],metadata=deepcopy(e['metadata'])) for e in list(known.values())[:2]])
            event.update(count_before=i+1,count_after=i+2)
            event['metadata']['source']['test_only']=False
            event['write_receipt']['metadata_sha256']=text_hash(canonical(event['metadata']))
            known[event['id']]=event
        validate_episode(outer,episode,steps,expected_seed=1,initial_records={old['id']:old},test_only=False)
        with self.assertRaises(ValueError):
            validate_episode(outer,episode,steps,expected_seed=2,initial_records={old['id']:old},test_only=False)

    def test_export_whitelist_excludes_database_and_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            good=['batch-result.json','service/service-console.txt','seed-00/console.txt',
                  'seed-00/live/manager/result.json','seed-00/live/manager/server-console.txt',
                  'seed-00/live/manager/traffic/episode/result.json',
                  'seed-00/live/manager/traffic/episode/step-0000.json']
            bad=['experiment-chroma/result.json','seed-00/live/manager/cache/result.json',
                 'service/hf_home/model.bin','seed-00/live/manager/traffic/episode/cache/step-0001.json']
            for name in good+bad:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('{}')
            self.assertEqual({p.relative_to(root).as_posix() for p in selected_files(root)},set(good))

    def test_python38_and_exact_seed_order(self):
        for name in ('run_memory_on_20seeds.py','collect_memory_batch.py','accept_memory_episode.py'):
            ast.parse((ROOT/'validation'/name).read_text(encoding='utf-8'),feature_version=(3,8))
        source=(ROOT/'validation/run_memory_on_20seeds.py').read_text(encoding='utf-8')
        self.assertIn('seeds=list(range(20))',source)
        self.assertNotIn('ssh',source)


if __name__=='__main__':
    unittest.main()
