"""Offline M22-R3 returned evidence audit; stdlib only, no DB/model access."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from validation.accept_memory_episode import validate_episode
from llm_controller.local_memory import canonical, text_hash, manifest
from llm_controller.memory_prompt import QUERY_SCHEMA
from llm_controller.output_schema import parse_action, parse_negotiation


def main():
    folder = Path(sys.argv[1]).resolve()
    hashes = {}
    for line in (folder/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        path = (folder/name).resolve()
        path.relative_to(folder)
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
        hashes[path.relative_to(folder).as_posix()] = digest
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    assert actual == set(hashes)|{'SHA256SUMS'}
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    acceptance, config = load(folder/'acceptance.json'), load(folder/'memory-config.json')
    source = (folder/'SOURCE.txt').read_text().strip()
    local = lambda remote: folder/Path(remote).relative_to(Path(source))
    manager = load(local(acceptance['manager_report']))
    episode_path = local(acceptance['episode_report'])
    episode = load(episode_path)
    paths = [local(p) for p in acceptance['step_reports']]
    assert len(paths) == 99 and paths == [episode_path.parent/n for n in episode['step_files']]
    assert set(paths) == set(episode_path.parent.glob('step-*.json'))
    steps = [load(p) for p in paths]
    validate_episode(manager, episode, steps)
    commit = (folder/'git-commit.txt').read_text().strip()
    assert commit == manager['git_commit'] == episode['git_commit'] == '23d53b6e28b7c23e8228838ca02e4678e17559de'
    assert episode['git_status'] == '' and manager['memory_session'] == episode['memory_session']
    assert config['manifest'] == manifest(QUERY_SCHEMA) and config['test_only'] is True
    assert config['store_path_sha256'] == text_hash(source+'/test-chroma')
    assert episode['memory_session']['config_sha256'] == text_hash((folder/'memory-config.json').read_text(encoding='utf-8'))
    assert acceptance['verified_writes'] == 396 and acceptance['actual_environment_steps'] == 99
    assert acceptance['final_snapshot_sha256'] == episode['memory_session']['final_snapshot_sha256']
    calls, queries, updates = [], [], []
    same_step_hits = 0
    action_counts = Counter()
    for step in steps:
        assert step['git_commit'] == commit
        for call in step['calls']:
            api, context = call['api_response'], call['context']
            choice, usage = api['choices'][0], api['usage']
            assert api['model'] == episode['model'] and choice['finish_reason'] == 'stop'
            assert choice['message']['content'] == call['raw_response'] and choice['message'].get('refusal') is None
            assert usage['prompt_tokens'] == call['token_budget']['input_tokens']
            assert usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
            assert 0 < usage['completion_tokens'] <= 256
            if call['stage'] == 'action':
                parsed = parse_action(call['raw_response'], context['vehicle_id'], context['available_actions'], scene='intersection')
                assert parsed == call['parsers']['strict']['value']
                action_counts[parsed['decision']] += 1
            else:
                parse_negotiation(call['raw_response'], context['pairs'])
            calls.append(call)
        for q, event, call in zip(step['memory_queries'], step['memory_updates'], step['calls'][1:]):
            assert q['query_sha256'] == text_hash(q['query']) and q['query'].strip() == event['text'].strip()
            assert q['candidate_sha256'] == text_hash(canonical(q['candidates']))
            assert q['final_prompt_sha256'] == text_hash(call['messages'][0]['content'])
            assert q['input_tokens'] == call['token_budget']['input_tokens']
            assert q['injected_ids'] == [h['id'] for h in q['candidates'][:q['injected_count']]]
            assert event['metadata']['source']['code_commit'] == commit
            assert event['metadata']['source']['episode_id'] == episode['episode_id']
            assert event['id'] == 'm22/{}/{}/{}'.format(episode['episode_id'], step['step_id'], q['vehicle_id'])
            assert event['write_receipt']['manifest'] == config['manifest']
            same_step_hits += sum(h['metadata']['source']['step_id'] == step['step_id'] for h in q['candidates'])
            queries.append(q)
            updates.append(event)
        assert [v['action_id'] for v in step['submitted_vehicle_actions']] == step['step_observation']['environment_action']
    server = local(acceptance['manager_report']).parent/'server-console.txt'
    console = server.read_text(encoding='utf-8')
    assert console.count('POST /v1/chat/completions HTTP/1.1" 200 OK') == len(calls) == 495
    assert 'Application shutdown complete.' in console
    final = steps[-1]
    result = dict(status='PASS', commit=commit, verified_manifest_files=len(hashes),
        steps=len(steps), calls=len(calls), writes=len(updates), queries=len(queries),
        simulated_seconds=sum(s['step_observation']['simulated_seconds'] for s in steps),
        action_counts=dict(action_counts), max_input_tokens=max(c['api_response']['usage']['prompt_tokens'] for c in calls),
        max_required_tokens=max(c['api_response']['usage']['prompt_tokens'] for c in calls)+256,
        excluded_memories=sum(q['excluded_count'] for q in queries),
        empty_conflict_writes=sum(e['text'].strip() == 'Conflict info is empty' for e in updates),
        unique_stored_texts=len({e['text'] for e in updates}), candidate_same_step_hits=same_step_hits,
        latency_by_stage={stage:dict(median_seconds=statistics.median(c['wall_seconds'] for c in calls if c['stage']==stage),
            max_seconds=max(c['wall_seconds'] for c in calls if c['stage']==stage)) for stage in ('action','negotiation')},
        any_cav_collision=any(s['info']['cav_crashed'] or any(v['crashed'] for v in s['final_vehicles']) for s in steps),
        final_info=final['info'], final_done=final['done'], final_reward=final['reward'],
        reward_sum=sum(s['reward'] for s in steps), shutdown=manager['shutdown'],
        memory_session=episode['memory_session'], evidence_sha256=hashes,
        limitation='Single seed integration evidence; no causal memory benefit, full traffic semantic validation or independent database inspection.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('evidence_sha256','memory_session')}, indent=2))


if __name__ == '__main__':
    main()
