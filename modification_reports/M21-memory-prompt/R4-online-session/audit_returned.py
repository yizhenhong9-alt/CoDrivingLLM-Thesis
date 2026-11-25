"""Audit R4 returned capture; no tokenizer/model/simulator imports."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, text_hash
from llm_controller.memory_prompt import QUERY_SCHEMA, INTRO, original_experience, original_query, MARKER
from llm_controller.output_schema import parse_action, parse_negotiation
from validation.accept_online_memory import validate_capture, require


def main():
    folder = ROOT.parent/'runs/m21-r4'
    accepted = json.loads((folder/'acceptance.json').read_text(encoding='utf-8'))
    config = json.loads((folder/'memory-config.json').read_text(encoding='utf-8'))
    paths = list((folder/'capture').glob('*.json'))
    require(len(paths) == 1, 'Expected one capture')
    capture = json.loads(paths[0].read_text(encoding='utf-8'))
    commit = (folder/'git-commit.txt').read_text(encoding='utf-8').strip()
    require(commit == capture['git_commit'] == '7a786a914a9c7f1a9e772cdc6b71bd708deb2cba', 'Commit mismatch')
    snapshot = config['snapshot_sha256']
    require(accepted['status'] == 'PASS' and accepted['sent_to_qwen'] is False and
            accepted['actual_environment_steps'] == 0 and accepted['snapshot_sha256'] == snapshot and
            accepted['tokenizer_reference_counts'] == [1129, 949], 'Acceptance mismatch')
    require(config['format'] == 'm21-r4-readonly-v1' and config['manifest'] == manifest(QUERY_SCHEMA) and
            config['port'] == 18082 and config['timeout'] == 30 and
            config['context_limit'] == 2048 and config['output_tokens'] == 256, 'Config mismatch')
    validate_capture(capture, snapshot)
    require(accepted['session'] == capture['memory_session'] and
            accepted['session']['config_sha256'] == text_hash((folder/'memory-config.json').read_text(encoding='utf-8')) and
            accepted['session']['token_checks'] == 9, 'Session receipt mismatch')
    fixture_path = ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json'
    fixture_hash = text_hash(fixture_path.read_text(encoding='utf-8'))
    fixtures = json.loads(fixture_path.read_text(encoding='utf-8'))['rows']
    negotiation = capture['calls'][0]
    require(parse_negotiation(negotiation['raw_response'], negotiation['context']['pairs']) ==
            negotiation['parsers']['strict']['value'], 'Negotiation parser mismatch')
    require(INTRO not in negotiation['messages'][0]['content'], 'Memory injected into negotiation')
    summary = []
    for call, receipt in zip(capture['calls'][1:], capture['memory_queries']):
        hits = receipt['candidates']
        require(receipt['manifest'] == config['manifest'] and receipt['candidate_count'] == 2 and
                receipt['injected_count'] == 2 and receipt['excluded_count'] == 0 and
                receipt['exclusion_reason'] is None and len(hits) == 2 and
                receipt['injected_ids'] == [hit['id'] for hit in hits] and
                receipt['candidate_sha256'] == text_hash(canonical(hits)), 'Candidates changed')
        for hit in hits:
            index = int(hit['id'].split('-')[1])
            require(index in (0, 1), 'Unknown fixture')
            metadata = dict(fixtures[index]['would_write']['metadata'], source=dict(
                test_only=True, fixture_index=index, fixture_sha256=fixture_hash))
            require(hit['metadata'] == metadata and hit['text'] == fixtures[index]['would_write']['page_content'],
                    'Original text/metadata changed')
            require(-1e-5 <= hit['distance'] <= 2+1e-5 and
                    abs(hit['score']-max(-1., min(1., 1-hit['distance']))) < 1e-8, 'Distance mismatch')
        prompt = call['messages'][0]['content']
        base = prompt.replace('\n'+INTRO+original_experience(hits)+'\n', '', 1)
        scenario = base.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
        require(receipt['query'] == original_query(scenario) and
                receipt['query_sha256'] == text_hash(receipt['query']), 'Query changed')
        expected_top = next('fixture-'+str(i) for i, row in enumerate(fixtures) if row['query'] == receipt['query'])
        require(hits[0]['id'] == expected_top, 'Top-1 differs from identical original template')
        parsed = parse_action(call['raw_response'], call['context']['vehicle_id'],
                              call['context']['available_actions'], scene='intersection')
        require(parsed == call['parsers']['strict']['value'], 'Action parser mismatch')
        summary.append(dict(vehicle_id=receipt['vehicle_id'], top1=expected_top,
                            injected_count=2, input_tokens=receipt['input_tokens'], fixture_action=parsed))
    require([row['vehicle_id'] for row in summary] == [3, 4, 5, 6], 'Vehicle coverage mismatch')
    require(capture['validated_actions'] == [1, 1, 1, 1] and not capture.get('submitted_vehicle_actions'),
            'Unexpected submitted actions')
    audit = dict(status='PASS', commit=commit, queries=4, fixture_calls=5, actual_environment_steps=0,
                 token_checks=9, tokenizer_reference_counts=[1129,949],
                 negotiation_input_tokens=negotiation['token_budget']['input_tokens'],
                 cases=summary, maximum_required_tokens=max(row['input_tokens'] for row in summary)+256,
                 snapshot_sha256=snapshot, session=capture['memory_session'],
                 evidence_sha256={path.relative_to(folder).as_posix(): text_hash(path.read_bytes().decode('utf-8'))
                     for path in [folder/'acceptance.json', folder/'memory-config.json', folder/'git-commit.txt', paths[0]]},
                 limitation='Fixture negotiation/action responses, not Qwen generation. Token counts audited from returned receipts, no local tokenizer rerun; service console/DB not supplied.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
