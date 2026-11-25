"""M21-R4 current-scenario readonly retrieval/count service, zero-step fixture flow."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import manifest, personal_path, canonical, text_hash
from llm_controller.memory_http import MemoryHTTPClient, QWEN_TOKENIZER
from llm_controller.memory_prompt import QUERY_SCHEMA, INTRO, MARKER, original_experience
from validation.memory_service_session import memory_service, offline_env


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_capture(report, expected_snapshot):
    require(report['status'] == 'validated_not_applied' and report['mode'] == 'fixture' and
            report['memory_mode'] == 'retrieve-only' and report['actual_environment_steps'] == 0 and
            report['memory_module_imported'] is False, 'Expected zero-step readonly fixture capture')
    session = report['memory_session']
    require(session['opened'] is True and session['closed'] is True and
            session['queries'] == 4 and session['final_snapshot_verified'] is True and
            session['expected_snapshot_sha256'] == expected_snapshot, 'Session lifecycle/corpus mismatch')
    require(len(report['calls']) == 5 and len(report['memory_queries']) == 4, 'Expected one negotiation and four CAV calls')
    for call in report['calls']:
        require(call['sent_to_model'] is False and call['parsers']['strict']['status'] == 'parsed', 'Unexpected model request or parser failure')
        budget = call['token_budget']
        require(budget['output_tokens'] == 256 and budget['context_limit'] == 2048 and
                budget['input_tokens']+256 <= 2048, 'Request token budget mismatch')
    actions = [call for call in report['calls'] if call['stage'] == 'action']
    require(report['calls'][0]['stage'] == 'negotiation' and len(actions) == 4, 'Call roles changed')
    for call, receipt in zip(actions, report['memory_queries']):
        prompt = call['messages'][0]['content']
        require(call['context']['vehicle_id'] == receipt['vehicle_id'] and
                text_hash(prompt) == receipt['final_prompt_sha256'] and
                receipt['snapshot_sha256'] == expected_snapshot and
                call['token_budget']['input_tokens'] == receipt['input_tokens'], 'Action prompt receipt mismatch')
        section = '\n'+INTRO+original_experience(receipt['candidates'][:receipt['injected_count']])+'\n'
        require(prompt.count(section+MARKER) == 1 and
                text_hash(prompt.replace(section, '', 1)) == receipt['base_prompt_sha256'], 'Base prompt altered')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18082)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            sys.version_info[:2] == (3, 8) and Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'),
            'Existing Spark sim Python 3.8 required')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    require(run.is_dir(), 'Fresh run directory required')
    fixture = (ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_bytes()
    rows = json.loads(fixture)['rows']
    expected = manifest(QUERY_SCHEMA)
    client = MemoryHTTPClient(expected, args.port)
    with memory_service(run/'create', run/'test-chroma', expected, args.port, create=True):
        for i, row in enumerate(rows):
            metadata = dict(row['would_write']['metadata'], source=dict(test_only=True, fixture_index=i,
                            fixture_sha256=text_hash(fixture.decode('utf-8'))))
            client.add('fixture-'+str(i), row['would_write']['page_content'], metadata)
        snapshot = client.status()['snapshot_sha256']
    with memory_service(run/'readonly', run/'test-chroma', expected, args.port, qwen_tokenizer=True):
        status = client.status()
        require(status['snapshot_sha256'] == snapshot and status['tokenizer'] == QWEN_TOKENIZER,
                'Readonly/count service identity mismatch')
        r2path = personal_path(Path('/home/nclab/Yizhen/runs/M21-R2-retrieval-prompt-6fIklV/acceptance.json'))
        raw = r2path.read_bytes()
        require(text_hash(raw.decode('utf-8')) == '28d4167ad41e4a2896ea579bab24c1dd646f188d251ad08afee455d222f0dfc2', 'Accepted R2 changed')
        counter_checks = []
        for record in json.loads(raw)['records']:
            count = client.count_messages(record['messages'])
            require(count == record['input_tokens'], 'Memory-env tokenizer differs from accepted Qwen count')
            counter_checks.append(count)
        config = dict(format='m21-r4-readonly-v1', manifest=expected, port=args.port, timeout=30,
                      snapshot_sha256=snapshot, context_limit=2048, output_tokens=256)
        config_path = run/'memory-config.json'
        config_path.write_text(canonical(config)+'\n', encoding='utf-8')
        capture = run/'capture'
        client_env = run/'client-env'
        client_env.mkdir()
        with (run/'capture-console.txt').open('x', encoding='utf-8') as output:
            subprocess.run(['/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python',
                            str(ROOT/'validation/run_qwen_single_step.py'), '--mode', 'fixture', '--parser', 'strict',
                            '--seed', '0', '--memory-config', str(config_path), '--output-dir', str(capture)],
                           cwd=str(ROOT), env=offline_env(client_env), stdout=output, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        reports = list(capture.glob('*.json'))
        require(len(reports) == 1, 'Expected one current-scenario capture')
        report = json.loads(reports[0].read_text(encoding='utf-8'))
        validate_capture(report, snapshot)
        require(client.status()['snapshot_sha256'] == snapshot, 'Readonly run changed corpus')
    result = dict(status='PASS', capture_report=str(reports[0]), tokenizer_reference_counts=counter_checks,
                  snapshot_sha256=snapshot, session=report['memory_session'],
                  actual_environment_steps=0, sent_to_qwen=False,
                  limitation='Current simulator scenario with fixture negotiation/actions; real readonly MiniLM/Chroma and tokenizer HTTP. No Qwen generation or M22 writes.')
    (run/'acceptance.json').write_text(canonical(result)+'\n', encoding='utf-8')
    print('M21-R4 online readonly memory: PASS; queries=4; LLM fixture calls=5; env.step=0')


if __name__ == '__main__':
    main()
