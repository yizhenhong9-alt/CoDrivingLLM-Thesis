"""M23-R1 copy-only offline retrieval probes; no add, Qwen, simulator or source DB open."""
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
from llm_controller.local_memory import canonical, personal_path, text_hash, vector
from validation.memory_service_session import offline_env


def inventory(folder):
    result={}
    for path in sorted(folder.rglob('*')):
        personal_path(path)
        if path.is_file():
            result[path.relative_to(folder).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='linux' or platform.machine()!='aarch64' or Path(sys.prefix)!=Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312'):
        raise RuntimeError('Existing Spark memory environment required')
    source,run=personal_path(args.source),personal_path(args.run_dir)
    db=personal_path(source/'experiment-chroma')
    if (db/'writer.lock').exists():
        raise RuntimeError('Source writer active or stale lock; stop and inspect, never remove automatically')
    before=inventory(db)
    clone=run/'database-copy'
    shutil.copytree(str(db),str(clone))
    if inventory(clone)!=before:
        raise ValueError('Copy mismatch')
    envdir=run/'runtime'
    envdir.mkdir()
    os.environ.update(offline_env(envdir))
    from validation.serve_local_memory import verified_snapshot
    from validation.serve_local_embedding import load_encoder
    from llm_controller.chroma_memory import ChromaMemoryStore
    config=json.loads((source/'memory-config.json').read_text())
    spec=config['manifest']
    snapshot=verified_snapshot(Path('/home/nclab/Yizhen/runs/M20-R6-minilm-acceptance-tNg6E3'))
    import torch
    if torch.version.cuda is not None:
        raise ValueError('CPU torch required')
    torch.set_num_threads(1)
    encode=load_encoder(snapshot,spec)
    queries={'\n Conflict info is empty'}
    for path in source.glob('seed-*/live/*/traffic/*/step-*.json'):
        step=json.loads(path.read_text())
        queries.update(q['query'] for q in step.get('memory_queries',[]))
        queries.update('\n'+e['text'] for e in step.get('memory_updates',[]))
    report=dict(source=str(source),source_file_hashes=before,
                scope='Probes of distinct recorded queries plus stored-text variants and empty query. Exact failed vehicle query was not persisted.',probes=[])
    safe_messages={'Invalid Chroma query result shape','Invalid cosine distance','Invalid/duplicate result ID',
                   'Missing source metadata','Embedding input exceeds 256 tokens'}
    with ChromaMemoryStore(clone,spec) as store:
        report.update(initial_count=store.count(),initial_snapshot=store.snapshot_sha256())
        for query in sorted(queries):
            row=dict(query_sha256=text_hash(query),query_chars=len(query),stage='encode')
            try:
                embedding=vector(encode([query])[0],spec['dimension'])
                row['stage']='raw-chroma-query'
                raw=store.collection.query(query_embeddings=[embedding],n_results=2,include=['documents','metadatas','distances'])
                row['distances']=raw.get('distances')
                row['column_lengths']={key:[len(v) for v in raw.get(key,[])] for key in ('ids','documents','metadatas','distances')}
                row['stage']='adapter-search'
                hits=store.search(embedding,2)
                row.update(status='PASS',hit_count=len(hits))
            except Exception as error:
                row.update(status='FAIL',error_type=type(error).__name__,
                           error_code=str(error) if str(error) in safe_messages else 'unclassified-no-message-logged')
            report['probes'].append(row)
        report.update(final_count=store.count(),final_snapshot=store.snapshot_sha256())
    report['source_unchanged']=before==inventory(db)
    report['logical_copy_unchanged']=(report['initial_count']==report['final_count'] and report['initial_snapshot']==report['final_snapshot'])
    (run/'diagnosis.json').write_text(canonical(report)+'\n',encoding='utf-8')
    print('Diagnostic probes completed; failures={}; source unchanged={}'.format(sum(p['status']=='FAIL' for p in report['probes']),report['source_unchanged']))
    if not report['source_unchanged'] or not report['logical_copy_unchanged']:
        raise ValueError('Unexpected mutation; retain evidence')


if __name__=='__main__':
    main()
