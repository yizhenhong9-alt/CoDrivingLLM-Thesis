"""Audit returned M22-R1 evidence offline; no models, database or network."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, text_hash
from llm_controller.memory_prompt import QUERY_SCHEMA
from validation.accept_original_memory import validate_original_capture


def main():
    folder = Path(sys.argv[1])
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    acceptance = read(folder/'acceptance.json')
    config = read(folder/'memory-config.json')
    commit = (folder/'git-commit.txt').read_text().strip()
    assert commit == 'd9abe48b0b3d63bf6164e70386be638fbb1df779'
    assert acceptance['status'] == 'PASS' and acceptance['final_count'] == 8
    assert acceptance['actual_environment_steps'] == 0 and acceptance['sent_to_qwen'] is False
    assert config['manifest'] == manifest(QUERY_SCHEMA) and config['test_only'] is True
    remote = '/home/nclab/Yizhen/runs/M22-R1-original-memory-GuYu06'
    assert config['store_path_sha256'] == text_hash(remote+'/test-chroma')
    known, previous, inputs, phases = {}, None, [], []
    for index in range(2):
        files = list((folder/('episode-scope-'+str(index+1))/'capture').glob('*.json'))
        assert len(files) == 1
        report = read(files[0])
        validate_original_capture(report, index*4)
        session = report['memory_session']
        assert report['git_commit'] == commit
        assert session['config_sha256'] == text_hash((folder/'memory-config.json').read_text(encoding='utf-8'))
        assert session['token_checks'] == 9 and session['test_only'] is True
        if previous is not None:
            assert session['initial_snapshot_sha256'] == previous
        for query, event, call in zip(report['memory_queries'], report['memory_updates'], report['calls'][1:]):
            assert query['manifest'] == config['manifest']
            assert query['query_sha256'] == text_hash(query['query'])
            assert query['query'].strip() == event['text'].strip()
            assert query['candidate_sha256'] == text_hash(canonical(query['candidates']))
            assert query['final_prompt_sha256'] == text_hash(call['messages'][0]['content'])
            assert query['input_tokens'] == call['token_budget']['input_tokens']
            assert query['injected_count'] == query['candidate_count'] and query['excluded_count'] == 0
            assert query['injected_ids'] == [h['id'] for h in query['candidates']]
            for hit in query['candidates']:
                prior = known[hit['id']]
                assert hit['text'] == prior['text'] and hit['metadata'] == prior['metadata']
            source = event['metadata']['source']
            assert source['code_commit'] == commit and source['episode_id'] == report['episode_id']
            assert source['step_id'] == 0 and source['vehicle_id'] == query['vehicle_id']
            assert source['comments_kind'] == 'original-generate-comment-heuristic-not-outcome'
            assert event['id'] == 'm22/{}/0/{}'.format(report['episode_id'], query['vehicle_id'])
            assert event['id'] not in known
            receipt = event['write_receipt']
            assert receipt['id'] == event['id'] and receipt['manifest'] == config['manifest']
            assert receipt['text_sha256'] == text_hash(event['text'])
            assert receipt['metadata_sha256'] == text_hash(canonical(event['metadata']))
            assert event['snapshot_before'] != event['snapshot_after']
            if event['text'].strip() == 'Conflict info is empty':
                assert event['metadata']['comments'] == 'recommended to FASTER'
            known[event['id']] = event
        previous = report['memory_updates'][-1]['snapshot_after']
        assert previous == session['final_snapshot_sha256'] == acceptance['phases'][index]['snapshot_sha256']
        inputs.extend(c['token_budget']['input_tokens'] for c in report['calls'])
        phases.append(dict(query_corpus_counts=[q['corpus_count'] for q in report['memory_queries']],
                           final_snapshot_sha256=previous))
    result = dict(status='PASS', commit=commit, phases=phases, unique_verified_writes=len(known),
                  input_tokens=inputs, max_required_tokens=max(inputs)+256,
                  actual_environment_steps=0, sent_to_qwen=False,
                  evidence_sha256={p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(folder.rglob('*')) if p.is_file()},
                  limitation='Returned JSON receipts audited; no independent database inspection or traffic/safety validation.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('M22-R1 returned evidence audit: PASS; unique writes=8; env.step=0')


if __name__ == '__main__':
    main()
