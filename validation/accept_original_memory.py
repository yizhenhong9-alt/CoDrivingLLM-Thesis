"""M22-R1 empty-store original on semantics across two zero-step fixture scopes."""
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
from validation.memory_service_session import memory_service, offline_env


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_original_capture(report, initial_count):
    require(report['status'] == 'validated_not_applied' and report['mode'] == 'fixture' and
            report['memory_mode'] == 'on' and report['actual_environment_steps'] == 0 and
            report['memory_module_imported'] is False, 'Expected original-on zero-step test capture')
    session = report['memory_session']
    require(session['opened'] is True and session['closed'] is True and session['writes'] == 4 and
            session['queries'] == 4 and session['initial_count'] == initial_count and
            session['final_count'] == initial_count+4 and session['final_snapshot_verified'] is True,
            'Original session counts/lifecycle mismatch')
    require(len(report['calls']) == 5 and len(report['memory_queries']) == 4 and
            len(report['memory_updates']) == 4, 'Expected 1 negotiation and 4 retrieve-answer-update sequences')
    for call in report['calls']:
        require(call['sent_to_model'] is False and call['parsers']['strict']['status'] == 'parsed' and
                call['token_budget']['input_tokens']+256 <= 2048, 'Fixture/parser/budget mismatch')
    queries, writes = report['memory_queries'], report['memory_updates']
    require([q['corpus_count'] for q in queries] == list(range(initial_count, initial_count+4)),
            'Previous vehicle write was not visible to following query')
    require([q['candidate_count'] for q in queries] == [min(2, n) for n in range(initial_count, initial_count+4)],
            'Unexpected original k=2 behavior')
    for index, (query, event, call) in enumerate(zip(queries, writes, report['calls'][1:])):
        metadata = event['metadata']
        require(event['status'] == 'verified' and event['count_before'] == initial_count+index and
                event['count_after'] == initial_count+index+1 and
                query['snapshot_sha256'] == event['snapshot_before'] and
                metadata['human_question'] == metadata['negotiation_result'] == 'None' and
                metadata['final_action'] == str([call['parsers']['strict']['value']['action_id']]) and
                metadata['source']['test_only'] is True and
                metadata['source']['method'] == 'original-per-vehicle-pre-step', 'Original write receipt mismatch')
        if index:
            require(query['snapshot_sha256'] == writes[index-1]['snapshot_after'], 'Snapshot sequence broken')
    if initial_count == 0:
        require(queries[0]['candidates'] == [] and queries[1]['candidates'][0]['id'] == writes[0]['id'],
                'First empty query or same-step first write visibility failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18082)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            sys.version_info[:2] == (3, 8) and Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'),
            'Existing Spark simulation Python 3.8 required')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    require(run.is_dir(), 'Fresh run directory required')
    expected = manifest(QUERY_SCHEMA)
    database = personal_path(run/'test-chroma')
    client = MemoryHTTPClient(expected, args.port)
    phases = []
    with memory_service(run/'service', database, expected, args.port, create=True, qwen_tokenizer=True):
        status = client.status()
        require(status['count'] == 0, 'New memory-on test store must start empty')
        config = dict(format='m22-original-v1', manifest=expected, port=args.port, timeout=30,
                      store_path_sha256=text_hash(database.as_posix()), context_limit=2048,
                      output_tokens=256, test_only=True)
        config_path = run/'memory-config.json'
        config_path.write_text(canonical(config)+'\n', encoding='utf-8')
        for number in (1, 2):
            phase = run/('episode-scope-'+str(number))
            phase.mkdir()
            output_dir = phase/'capture'
            with (phase/'console.txt').open('x', encoding='utf-8') as output:
                subprocess.run(['/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python',
                    str(ROOT/'validation/run_qwen_single_step.py'), '--mode', 'fixture', '--parser', 'strict',
                    '--seed', '0', '--memory', 'on', '--memory-config', str(config_path),
                    '--output-dir', str(output_dir)], cwd=str(ROOT), env=offline_env(phase),
                    stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)
            files = list(output_dir.glob('*.json'))
            require(len(files) == 1, 'Expected one original-on capture per scope')
            report = json.loads(files[0].read_text(encoding='utf-8'))
            initial_count = 4*(number-1)
            validate_original_capture(report, initial_count)
            status = client.status()
            require(status['count'] == initial_count+4 and
                    status['snapshot_sha256'] == report['memory_session']['final_snapshot_sha256'],
                    'Service corpus differs from scope writes')
            phases.append(dict(capture_report=str(files[0]), initial_count=initial_count,
                final_count=status['count'], query_corpus_counts=[q['corpus_count'] for q in report['memory_queries']],
                candidate_counts=[q['candidate_count'] for q in report['memory_queries']],
                snapshot_sha256=status['snapshot_sha256']))
    result = dict(status='PASS', phases=phases, initial_count=0, final_count=8,
                  actual_environment_steps=0, sent_to_qwen=False,
                  limitation='Two fresh fixture capture scopes, same shared test store. Original per-vehicle updates; no real Qwen, env.step or episode outcomes.')
    (run/'acceptance.json').write_text(canonical(result)+'\n', encoding='utf-8')
    print('M22-R1 original memory on: PASS; query corpus counts=0,1,2,3 / 4,5,6,7; writes=8; env.step=0')


if __name__ == '__main__':
    main()
