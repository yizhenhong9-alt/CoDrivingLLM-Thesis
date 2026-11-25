"""M21-R3 frozen real-retrieval prompt replay; stdlib, no simulator imports."""
import json
from pathlib import Path
from .local_memory import canonical, personal_path, text_hash, manifest
from .memory_prompt import QUERY_SCHEMA, original_query
from .qwen_step import MODEL
from .output_schema import parse_action


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_config(path):
    path = personal_path(path)
    config = json.loads(path.read_text(encoding='utf-8'))
    require(config['format'] == 'm21-r3-frozen-retrieval-v1' and
            config['model'] == MODEL and config['context_limit'] == 2048 and
            config['output_tokens'] == 256, 'Unsupported memory replay config')
    artifacts = {}
    for name in ('acceptance', 'counts', 'commit'):
        entry = config['artifacts'][name]
        source = personal_path(Path(entry['path']))
        raw = source.read_bytes()
        require(text_hash(raw.decode('utf-8')) == entry['sha256'], 'Replay source hash mismatch: '+name)
        artifacts[name] = raw.decode('utf-8')
    require(artifacts['commit'].strip() == 'd3626020622939f6e3074bf131e2dbb6d309002c', 'Expected accepted R2 commit')
    accepted, counts = json.loads(artifacts['acceptance']), json.loads(artifacts['counts'])
    require(accepted['status'] == counts['status'] == 'PASS' and
            accepted['manifest'] == manifest(QUERY_SCHEMA) and len(accepted['records']) == 2 and
            accepted['oversize_minilm_rejected_without_write'] is True,
            'Expected successful two-case R2 bundle')
    from .memory_prompt import INTRO, MARKER, original_experience
    cases, prepared = [], []
    seen = set()
    for record in accepted['records']:
        source = personal_path(Path(record['source_step']))
        raw = source.read_bytes()
        require(text_hash(raw.decode('utf-8')) == record['source_step_sha256'], 'M16 source changed')
        step = json.loads(raw)
        require(step['model'] == MODEL and step['memory_mode'] == 'off', 'Expected original off source')
        calls = [c for c in step['calls'] if c['stage'] == 'action' and
                 c['context']['vehicle_id'] == record['vehicle_id']]
        require(len(calls) == 1 and source.name not in seen, 'Ambiguous replay case')
        seen.add(source.name)
        call = calls[0]
        require(len(call['messages']) == 1 and call['messages'][0]['role'] == 'system', 'Expected system prompt')
        base = call['messages'][0]['content']
        require(text_hash(base) == record['base_prompt_sha256'], 'Base prompt changed')
        scenario = base.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
        require(record['query'] == original_query(scenario) and
                record['query_sha256'] == text_hash(record['query']), 'Replay query changed')
        hits = record['candidates']
        require(record['candidate_sha256'] == text_hash(canonical(hits)) and
                record['snapshot_sha256'] == accepted['snapshot_sha256'] and
                record['manifest'] == accepted['manifest'], 'Replay corpus changed')
        require(record['output_tokens'] == 256 and record['context_limit'] == 2048 and
                record['injected_count'] == 2 and record['candidate_count'] == 2 and
                record['excluded_count'] == 0 and record['injected_ids'] == [h['id'] for h in hits],
                'Expected accepted two-hit prompt')
        require(len(hits) == 2 and all(h['metadata']['source']['test_only'] is True for h in hits),
                'Only test-only R2 memories supported')
        prompt = base.replace(MARKER, '\n'+INTRO+original_experience(hits)+'\n'+MARKER, 1)
        require(record['messages'] == [dict(role='system', content=prompt)] and
                record['final_prompt_sha256'] == text_hash(prompt), 'Replay prompt changed')
        count = counts['counts'][text_hash(canonical(record['messages']))]
        require(type(count) is int and count == record['input_tokens'] and count+256 <= 2048,
                'Replay token receipt mismatch')
        cases.append(dict(scenario=scenario, base_prompt=base, hits=hits,
                          source_step=record['source_step'], source_step_sha256=record['source_step_sha256'],
                          vehicle_id=record['vehicle_id']))
        prepared.append(dict(messages=record['messages'], context=call['context'],
                             input_tokens=count, memory_receipt=record))
    require(text_hash(canonical(cases)+'\n') == counts['cases_sha256'], 'Token source cases hash mismatch')
    return dict(config=config, cases=prepared, snapshot_sha256=accepted['snapshot_sha256'],
                config_sha256=text_hash(path.read_text(encoding='utf-8')))


def validate_result(report):
    require(report.get('status') == 'memory_responses_validated' and
            report.get('actual_environment_steps') == 0 and report.get('qwen_calls') == 2 and
            len(report.get('calls', [])) == 2 and
            all('parsed_action' in call for call in report['calls']), 'Memory replay validation failed')


def run_replay(bundle, transport, report, persist):
    require(transport.mode == 'live' and transport.max_tokens == 256, 'Explicit live Qwen transport required')
    report.update(status='running', actual_environment_steps=0, qwen_calls=0, calls=[],
                  memory_mode='frozen-test-retrieval-replay', config_sha256=bundle['config_sha256'],
                  snapshot_sha256=bundle['snapshot_sha256'],
                  limitation='Two saved real retrieval prompts; no current simulator, online retrieval, negotiation call, writes or traffic steps.')
    for case in bundle['cases']:
        entry = dict(messages=case['messages'], context=case['context'],
                     memory_receipt=case['memory_receipt'], input_tokens=case['input_tokens'])
        report['calls'].append(entry)
        report['qwen_calls'] += 1
        persist(report)
        try:
            raw = transport.complete(entry['messages'], 'action', entry['context'])
            entry['raw_response'] = raw
            entry['parsed_action'] = parse_action(raw, entry['context']['vehicle_id'],
                                                 entry['context']['available_actions'], scene='intersection')
        except Exception as exc:
            entry['error'] = type(exc).__name__+': '+str(exc)
            report['status'] = 'failed'
            raise
        finally:
            entry['api_response'] = transport.last_response
            persist(report)
    report['status'] = 'memory_responses_validated'
    persist(report)
