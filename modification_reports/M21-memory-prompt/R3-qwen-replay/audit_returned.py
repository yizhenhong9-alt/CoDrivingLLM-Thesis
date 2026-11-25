"""M21-R3 returned artifact audit; stdlib only, never model/network execution."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, text_hash
from llm_controller.memory_replay import require, validate_result
from llm_controller.output_schema import parse_action
from llm_controller.qwen_step import MODEL
from validation.run_qwen_live_session import launch_args, REVISION


def main():
    folder = ROOT.parent/'runs/m21-r3'
    previous = ROOT.parent/'runs/m21-r2'
    def read(name):
        return json.loads((folder/name).read_text(encoding='utf-8'))
    outer, traffic = read('live/result.json'), read('live/traffic/result.json')
    config, preflight = read('replay-config.json'), read('preflight.json')
    commit = (folder/'git-commit.txt').read_text(encoding='utf-8').strip()
    require(commit == outer['git_commit'] == 'cd9eef4e396babe7db59720e1bd6f5bb67804bdb', 'Commit mismatch')
    require(outer['status'] == 'responses_validated' and outer['traffic_exit_code'] == 0 and
            outer['observed_environment_steps'] == 0 and not outer['apply_step'] and
            not outer['project_entry'] and outer['model_started'] is True, 'Outer state mismatch')
    require(outer['model'] == config['model'] == MODEL and outer['expected_revision'] == REVISION,
            'Model/revision mismatch')
    # Path() renders Linux constants using Windows separators in this local audit.
    expected_launch = [value.replace('\\', '/') for value in launch_args()]
    require(outer['launch']['args'] == expected_launch, 'Launch settings changed')
    command = outer['traffic_command']
    require(any(str(x).endswith('/validation/run_memory_prompt_replay.py') for x in command) and
            '--apply-step' not in command and '--project-entry' not in command, 'Wrong client command')
    require(config['format'] == 'm21-r3-frozen-retrieval-v1' and
            config['output_tokens'] == 256 and config['context_limit'] == 2048, 'Config format/budget mismatch')
    for key, name in (('acceptance', 'acceptance.json'), ('counts', 'counts.json'), ('commit', 'git-commit.txt')):
        require(text_hash((previous/name).read_bytes().decode('utf-8')) == config['artifacts'][key]['sha256'],
                'Prior R2 artifact hash mismatch: '+key)
    config_hash = text_hash((folder/'replay-config.json').read_text(encoding='utf-8'))
    require(config_hash == preflight['config_sha256'] == traffic['config_sha256'] and
            preflight['status'] == 'PASS' and preflight['expected_revision'] == REVISION, 'Preflight mismatch')
    r2 = json.loads((previous/'acceptance.json').read_text(encoding='utf-8'))
    require(traffic['snapshot_sha256'] == r2['snapshot_sha256'], 'Corpus snapshot mismatch')
    validate_result(traffic)
    rows = []
    for index, (call, original) in enumerate(zip(traffic['calls'], r2['records'])):
        require(call['messages'] == original['messages'] and call['memory_receipt'] == original and
                call['input_tokens'] == original['input_tokens'] == preflight['input_tokens'][index],
                'Prompt or memory receipt changed')
        # Verify original available actions, not merely the returned context.
        source = list((ROOT.parent/'runs/M16-one-episode').rglob(Path(original['source_step']).name))
        require(len(source) == 1, 'Ambiguous original M16 source')
        raw_source = source[0].read_bytes()
        require(text_hash(raw_source.decode('utf-8')) == original['source_step_sha256'], 'M16 source hash mismatch')
        source_calls = [c for c in json.loads(raw_source)['calls'] if c['stage'] == 'action' and
                        c['context']['vehicle_id'] == original['vehicle_id']]
        require(len(source_calls) == 1 and call['context'] == source_calls[0]['context'], 'Available actions changed')
        api = call['api_response']
        require(api['model'] == MODEL and len(api['choices']) == 1, 'API model/choice mismatch')
        choice = api['choices'][0]
        require(choice['finish_reason'] == 'stop' and not choice['message'].get('refusal') and
                choice['message']['content'] == call['raw_response'], 'API/raw response mismatch')
        parsed = parse_action(call['raw_response'], call['context']['vehicle_id'],
                              call['context']['available_actions'], scene='intersection')
        require(parsed == call['parsed_action'], 'Strict parser result mismatch')
        usage = api['usage']
        require(usage['prompt_tokens'] == call['input_tokens'] and
                type(usage['completion_tokens']) is int and 0 < usage['completion_tokens'] <= 256 and
                usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens'] and
                usage['total_tokens'] <= 2048, 'Actual API usage mismatch')
        rows.append(dict(case=index, vehicle_id=parsed['vehicle_id'], decision=parsed['decision'],
                         action_id=parsed['action_id'], usage=usage, finish_reason=choice['finish_reason'],
                         prompt_sha256=text_hash(canonical(call['messages']))))
    shutdown = outer['shutdown']
    require(shutdown['exited'] is True and shutdown['exit_code'] == 0 and
            shutdown['remaining_known_processes'] == [] and shutdown['port_closed'] is True and
            shutdown['warnings'] == [] and shutdown['clean_observation'] is True and
            not outer.get('client_still_running'), 'Shutdown incomplete')
    audit = dict(status='PASS', commit=commit, qwen_calls=2, actual_environment_steps=0,
                 cases=rows, shutdown=shutdown, snapshot_sha256=traffic['snapshot_sha256'],
                 evidence_sha256={name: text_hash((folder/name).read_bytes().decode('utf-8')) for name in
                    ('git-commit.txt', 'preflight.json', 'replay-config.json', 'live/result.json', 'live/traffic/result.json')},
                 limitation='Two frozen real retrieval prompts; no online retrieval or traffic/safety validation. Shutdown fields verified in result.json, raw server console not supplied.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
