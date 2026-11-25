"""Audit returned M22-R2 evidence, explicitly retaining missing manager evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, text_hash, manifest
from llm_controller.memory_prompt import QUERY_SCHEMA
from llm_controller.output_schema import parse_action, parse_negotiation
from validation.accept_memory_live_step import validate_live_step


def main():
    folder = Path(sys.argv[1])
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    acceptance, config = load(folder/'acceptance.json'), load(folder/'memory-config.json')
    episodes = list((folder/'traffic').glob('*/result.json'))
    assert len(episodes) == 1
    episode = load(episodes[0])
    step = load(episodes[0].parent/'step-0000.json')
    manager = load(folder/'live/result.json')
    validate_live_step(manager, episode, step)
    commit = (folder/'git-commit.txt').read_text().strip()
    assert commit == episode['git_commit'] == step['git_commit'] == '8980e7eb5bcdbe8ec849a4ae8ec38033201d6ccc'
    assert manager['git_commit'] == commit and manager['memory_session'] == episode['memory_session']
    assert manager['traffic_report'] == acceptance['episode_report']
    assert manager['memory_mode'] == 'on' and manager['project_entry'] is True
    assert manager['observed_environment_steps'] == manager['max_steps'] == 1
    launch = manager['launch']['args']
    for flag, value in {'--host': '127.0.0.1', '--port': '18080', '--max-model-len': '2048',
                        '--gpu-memory-utilization': '0.40', '--kv-cache-memory-bytes': '536870912',
                        '--moe-backend': 'triton', '--shutdown-timeout': '30'}.items():
        assert launch[launch.index(flag)+1] == value
    assert manager['expected_revision'] == '5a5a776300a41aaa681dd7ff0106608ef2bc90db'
    assert episode['git_status'] == '' and episode['seed'] == 0 and episode['memory_mode'] == 'on'
    assert episode['status'] == 'step_limit_reached' and episode['actual_environment_steps'] == 1
    assert episode['memory_module_imported'] is False and episode['step_files'] == ['step-0000.json']
    assert step['status'] == 'single_step_complete' and step['actual_environment_steps'] == 1
    assert step['mode'] == 'live' and len(step['calls']) == 5
    assert config['manifest'] == manifest(QUERY_SCHEMA) and config['test_only'] is True
    session = episode['memory_session']
    assert session['config_sha256'] == text_hash((folder/'memory-config.json').read_text(encoding='utf-8'))
    assert session['opened'] and session['closed'] and session['final_snapshot_verified']
    assert session['initial_count'] == 0 and session['final_count'] == session['queries'] == session['writes'] == 4
    assert session['token_checks'] == 9
    calls = []
    for call in step['calls']:
        api = call['api_response']
        choice, usage = api['choices'][0], api['usage']
        assert call['sent_to_model'] is True and api['model'] == episode['model']
        assert choice['finish_reason'] == 'stop' and choice['message']['content'] == call['raw_response']
        assert choice['message'].get('refusal') is None
        assert usage['prompt_tokens'] == call['token_budget']['input_tokens']
        assert usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
        assert 0 < usage['completion_tokens'] <= 256 and usage['prompt_tokens']+256 <= 2048
        context = call['context']
        if call['stage'] == 'action':
            parsed = parse_action(call['raw_response'], context['vehicle_id'], context['available_actions'], scene='intersection')
        else:
            parsed = parse_negotiation(call['raw_response'], context['pairs'])
        assert call['parsers']['strict']['status'] == 'parsed'
        calls.append(dict(stage=call['stage'], vehicle_id=context.get('vehicle_id'),
                          raw_response=call['raw_response'], usage=usage, wall_seconds=call['wall_seconds']))
    known, previous = {}, session['initial_snapshot_sha256']
    for i, (q, event, call) in enumerate(zip(step['memory_queries'], step['memory_updates'], step['calls'][1:])):
        assert q['corpus_count'] == i and q['candidate_count'] == min(i, 2)
        assert q['injected_count'] == min(i, 2) and q['excluded_count'] == 0
        assert q['query_sha256'] == text_hash(q['query']) and q['query'].strip() == event['text'].strip()
        assert q['candidate_sha256'] == text_hash(canonical(q['candidates']))
        assert q['final_prompt_sha256'] == text_hash(call['messages'][0]['content'])
        assert q['snapshot_sha256'] == event['snapshot_before'] == previous
        for hit in q['candidates']:
            assert hit['text'] == known[hit['id']]['text'] and hit['metadata'] == known[hit['id']]['metadata']
        meta, receipt = event['metadata'], event['write_receipt']
        assert event['status'] == 'verified' and event['count_before'] == i and event['count_after'] == i+1
        assert meta['human_question'] == meta['negotiation_result'] == 'None'
        assert meta['final_action'] == str([call['parsers']['strict']['value']['action_id']])
        source = meta['source']
        assert source['code_commit'] == commit and source['episode_id'] == episode['episode_id']
        assert source['step_id'] == 0 and source['vehicle_id'] == q['vehicle_id'] and source['test_only'] is True
        assert source['method'] == 'original-per-vehicle-pre-step'
        assert event['id'] == 'm22/{}/0/{}'.format(episode['episode_id'], q['vehicle_id']) and event['id'] not in known
        assert receipt['id'] == event['id'] and receipt['manifest'] == config['manifest']
        assert receipt['text_sha256'] == text_hash(event['text']) and receipt['metadata_sha256'] == text_hash(canonical(meta))
        known[event['id']], previous = event, event['snapshot_after']
    assert previous == session['final_snapshot_sha256'] == acceptance['final_snapshot_sha256']
    assert [x['action_id'] for x in step['submitted_vehicle_actions']] == step['step_observation']['environment_action'] == [4, 3, 1, 3]
    server = (folder/'live/server-console.txt').read_text(encoding='utf-8')
    assert server.count('POST /v1/chat/completions HTTP/1.1" 200 OK') == 5
    assert 'Application shutdown complete.' in server
    assert not any(word in server for word in ('EngineDeadError', 'Traceback', 'force killing', 'Force killing'))
    result = dict(status='PASS', commit=commit,
        calls=calls, max_required_tokens=max(c['usage']['prompt_tokens'] for c in calls)+256,
        query_corpus_counts=[q['corpus_count'] for q in step['memory_queries']],
        verified_writes=len(known), step_observation=step['step_observation'], reward=step['reward'],
        done=step['done'], info=step['info'], final_vehicles=step['final_vehicles'],
        manager_report=acceptance['manager_report'], shutdown=manager['shutdown'],
        limitation='Returned manager observations and logs agree. No direct Spark process/DB inspection or safety-effect claim.',
        evidence_sha256={p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(folder.rglob('*')) if p.is_file()})
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
