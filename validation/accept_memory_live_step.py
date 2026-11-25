"""M22-R2: one real Qwen project-entry step with a fresh writable memory store."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, personal_path, text_hash
from llm_controller.memory_http import MemoryHTTPClient
from llm_controller.memory_prompt import QUERY_SCHEMA
from validation.memory_service_session import memory_service


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_live_step(outer, episode, step):
    require(outer['status'] in ('project_step_limit_reached', 'project_episode_terminal') and
            outer['traffic_exit_code'] == 0, 'Live project entry failed')
    shutdown = outer['shutdown']
    require(shutdown['exit_code'] == 0 and shutdown['clean_observation'] is True and
            shutdown['port_closed'] is True and shutdown['remaining_known_processes'] == [] and
            shutdown['warnings'] == [], 'Qwen shutdown requires manual review')
    require(episode['memory_mode'] == 'on' and episode['entry_point'] == 'Run_multi_CAV_LLM.py' and
            episode['seed'] == 0 and episode['actual_environment_steps'] == 1 and
            episode['memory_module_imported'] is False and len(episode['step_files']) == 1,
            'Expected exactly one original-memory project-entry step')
    session = episode['memory_session']
    require(session['opened'] is True and session['closed'] is True and
            session['final_snapshot_verified'] is True and session['initial_count'] == 0 and
            session['final_count'] == session['writes'] == session['queries'] == 4,
            'Original memory session receipt mismatch')
    require(step['status'] == 'single_step_complete' and step['actual_environment_steps'] == 1 and
            len(step['calls']) == 5 and len(step['memory_updates']) == 4 and
            len(step['memory_queries']) == 4, 'Step/call counts mismatch')
    require([q['corpus_count'] for q in step['memory_queries']] == [0, 1, 2, 3],
            'Original per-vehicle write visibility failed')
    known = {}
    previous = session['initial_snapshot_sha256']
    for call in step['calls']:
        require(call['sent_to_model'] is True and call['parsers']['strict']['status'] == 'parsed' and
                call['token_budget']['input_tokens']+256 <= 2048, 'Live parser/token budget failure')
    for index, (query, event, call) in enumerate(zip(step['memory_queries'], step['memory_updates'], step['calls'][1:])):
        require(query['snapshot_sha256'] == event['snapshot_before'] == previous and
                event['status'] == 'verified' and event['count_before'] == index and
                event['count_after'] == index+1 and query['candidate_count'] == min(index, 2),
                'Write sequence mismatch')
        for hit in query['candidates']:
            require(hit['id'] in known and hit['text'] == known[hit['id']]['text'] and
                    hit['metadata'] == known[hit['id']]['metadata'], 'Candidate source mismatch')
        meta, receipt = event['metadata'], event['write_receipt']
        require(meta['human_question'] == meta['negotiation_result'] == 'None' and
                meta['final_action'] == str([call['parsers']['strict']['value']['action_id']]) and
                meta['source']['test_only'] is True and
                meta['source']['method'] == 'original-per-vehicle-pre-step' and
                receipt['id'] == event['id'] and event['id'] not in known and
                receipt['text_sha256'] == text_hash(event['text']) and
                receipt['metadata_sha256'] == text_hash(canonical(meta)), 'Original write/source/hash mismatch')
        known[event['id']] = event
        previous = event['snapshot_after']
    require(previous == session['final_snapshot_sha256'], 'Final snapshot mismatch')


def main(_episode=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            sys.version_info[:2] == (3, 8) and
            Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'), 'Existing Spark sim environment required')
    run = personal_path(args.run_dir)
    personal_path(ROOT)
    require(run.is_dir(), 'Fresh run directory required')
    database, expected = personal_path(run/'test-chroma'), manifest(QUERY_SCHEMA)
    client = MemoryHTTPClient(expected, 18082)
    with memory_service(run/'service', database, expected, 18082, create=True, qwen_tokenizer=True):
        require(client.status()['count'] == 0, 'Fresh empty store required')
        config = dict(format='m22-original-v1', manifest=expected, port=18082, timeout=30,
                      store_path_sha256=text_hash(database.as_posix()), context_limit=2048,
                      output_tokens=256, test_only=True)
        config_path = run/'memory-config.json'
        config_path.write_text(canonical(config)+'\n', encoding='utf-8')
        # Existing manager owns startup/shutdown. No new Qwen deployment or model loading here.
        command = ['/home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python', '-B',
                   str(ROOT/'validation/run_qwen_live_session.py'), '--output-dir', str(run/'live'),
                   '--project-entry', '--seed', '0', '--max-steps', '300' if _episode else '1',
                   '--wall-seconds', '3600' if _episode else '600',
                   '--memory', 'on', '--memory-config', str(config_path)]
        # No outer timeout: let the existing manager complete its owned shutdown path.
        code = subprocess.run(command, cwd=str(ROOT)).returncode
        require(code == 0, 'Live manager failed; retain logs, do not retry automatically')
        files = list((run/'live').glob('*/result.json'))
        require(len(files) == 1, 'Expected one live manager report')
        outer = json.loads(files[0].read_text(encoding='utf-8'))
        episode_path = personal_path(Path(outer['traffic_report']))
        episode = json.loads(episode_path.read_text(encoding='utf-8'))
        step_paths = [personal_path(episode_path.parent/name) for name in episode['step_files']]
        steps = [json.loads(path.read_text(encoding='utf-8')) for path in step_paths]
        if _episode:
            from validation.accept_memory_episode import validate_episode
            validate_episode(outer, episode, steps)
        else:
            require(len(steps) == 1, 'Expected one step report')
            validate_live_step(outer, episode, steps[0])
        status = client.status()
        require(status['count'] == episode['memory_session']['final_count'] and
                status['snapshot_sha256'] == episode['memory_session']['final_snapshot_sha256'],
                'Service final corpus mismatch')
    result = dict(status='PASS', seed=0, actual_environment_steps=len(steps), verified_writes=status['count'],
                  manager_report=str(files[0]), episode_report=str(episode_path),
                  step_reports=[str(path) for path in step_paths],
                  final_snapshot_sha256=status['snapshot_sha256'],
                  limitation=('Single seed0 terminal episode; terminal does not imply successful arrival or safety improvement.' if _episode else
                  'One real Qwen step in an isolated test store; no completed episode, seed study or safety/effectiveness claim.'))
    if not _episode:
        result['step_report'] = str(step_paths[0])
    (run/'acceptance.json').write_text(canonical(result)+'\n', encoding='utf-8')
    print('{} real Qwen memory on: PASS; seed=0; writes={}; env.step={}'.format(
        'M22-R3' if _episode else 'M22-R2', status['count'], len(steps)))


if __name__ == '__main__':
    main()
