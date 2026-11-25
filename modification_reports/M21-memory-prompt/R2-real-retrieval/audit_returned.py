"""Audit returned R2 files without loading any model/tokenizer."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, manifest, text_hash
from llm_controller.memory_prompt import QUERY_SCHEMA, original_query, original_experience, INTRO, MARKER


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    folder = ROOT.parent/'runs/m21-r2'
    result = json.loads((folder/'acceptance.json').read_text(encoding='utf-8'))
    counts = json.loads((folder/'counts.json').read_text(encoding='utf-8'))
    commit = (folder/'git-commit.txt').read_text(encoding='utf-8').strip()
    require(commit == 'd3626020622939f6e3074bf131e2dbb6d309002c', 'Commit mismatch')
    require(result['status'] == counts['status'] == 'PASS', 'Status mismatch')
    require(result['manifest'] == manifest(QUERY_SCHEMA), 'Manifest mismatch')
    require(result['oversize_minilm_rejected_without_write'] is True, 'Missing long-input rejection')
    fixture_path = ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json'
    fixture_hash = text_hash(fixture_path.read_text(encoding='utf-8'))
    fixtures = json.loads(fixture_path.read_text(encoding='utf-8'))['rows']
    require(len(result['records']) == 2, 'Expected two records')
    cases, summary = [], []
    used_counts = {}
    for i, record in enumerate(result['records']):
        require(Path(record['source_step']).name == 'step-{:04d}.json'.format(fixtures[i]['step_id']), 'Wrong step')
        files = list((ROOT.parent/'runs/M16-one-episode').rglob(Path(record['source_step']).name))
        require(len(files) == 1, 'Ambiguous local M16')
        raw = files[0].read_bytes()
        require(text_hash(raw.decode('utf-8')) == record['source_step_sha256'], 'M16 hash mismatch')
        step = json.loads(raw)
        calls = [c for c in step['calls'] if c['stage'] == 'action' and
                 c['context']['vehicle_id'] == record['vehicle_id']]
        require(len(calls) == 1 and record['vehicle_id'] == 3, 'Wrong vehicle')
        base = calls[0]['messages'][0]['content']
        scenario = base.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
        require(record['query'] == original_query(scenario) == fixtures[i]['query'], 'Query mismatch')
        require(record['query_sha256'] == text_hash(record['query']), 'Query hash mismatch')
        hits = record['candidates']
        require(len(hits) == 2 and hits[0]['id'] == 'fixture-'+str(i), 'Top-1 mismatch')
        require({h['id'] for h in hits} == {'fixture-0', 'fixture-1'}, 'Candidate IDs mismatch')
        for hit in hits:
            index = int(hit['id'].split('-')[1])
            expected = dict(fixtures[index]['would_write']['metadata'], source=dict(
                test_only=True, fixture_index=index, fixture_sha256=fixture_hash))
            require(hit['text'] == fixtures[index]['would_write']['page_content'] and
                    hit['metadata'] == expected, 'Original text/metadata mismatch')
            distance, score = hit['distance'], hit['score']
            require(math.isfinite(distance) and -1e-5 <= distance <= 2+1e-5 and
                    abs(score-max(-1., min(1., 1-distance))) < 1e-8, 'Distance/score mismatch')
        require(record['manifest'] == result['manifest'] and
                record['snapshot_sha256'] == result['snapshot_sha256'], 'Snapshot/manifest mismatch')
        require(record['candidate_sha256'] == text_hash(canonical(hits)), 'Candidate hash mismatch')
        require(record['candidate_count'] == record['injected_count'] == 2 and
                record['excluded_count'] == 0 and record['exclusion_reason'] is None, 'Injection counts mismatch')
        require(record['injected_ids'] == [h['id'] for h in hits], 'Injection order mismatch')
        prompt = base.replace(MARKER, '\n'+INTRO+original_experience(hits)+'\n'+MARKER, 1)
        require(record['messages'] == [dict(role='system', content=prompt)] and
                record['base_prompt_sha256'] == text_hash(base) and
                record['final_prompt_sha256'] == text_hash(prompt), 'Prompt changed')
        require(record['output_tokens'] == 256 and record['context_limit'] == 2048, 'Budget changed')
        for size in (2, 1, 0):
            text = base.replace(MARKER, '\n'+INTRO+original_experience(hits[:size])+'\n'+MARKER, 1)
            key = text_hash(canonical([dict(role='system', content=text)]))
            require(type(counts['counts'][key]) is int and counts['counts'][key] > 0, 'Missing exact-message count')
            used_counts[key] = counts['counts'][key]
        require(record['input_tokens'] == counts['counts'][text_hash(canonical(record['messages']))] and
                record['input_tokens']+256 <= 2048, 'Token budget mismatch')
        require(record['attempts'] == [dict(memory_count=2, input_tokens=record['input_tokens'],
                                          required_tokens=record['input_tokens']+256)], 'Attempts mismatch')
        cases.append(dict(scenario=scenario, base_prompt=base, hits=hits, source_step=record['source_step'],
                          source_step_sha256=record['source_step_sha256'], vehicle_id=record['vehicle_id']))
        summary.append(dict(step=fixtures[i]['step_id'], top1=hits[0]['id'],
                            input_tokens=record['input_tokens'], injected_count=2))
    require(counts['cases_sha256'] == text_hash(canonical(cases)+'\n'), 'Tokenizer input receipt mismatch')
    require(counts['counts'] == used_counts, 'Unexpected/missing tokenizer cases')
    audit = dict(status='PASS', commit=commit, cases=summary, exact_message_token_counts_verified=6,
                 snapshot_sha256=result['snapshot_sha256'],
                 evidence_sha256={name: text_hash((folder/name).read_bytes().decode('utf-8'))
                                  for name in ('acceptance.json', 'counts.json', 'git-commit.txt')},
                 limitation='Audits returned evidence and local original M16; no independent ML/tokenizer rerun or live Qwen validation.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
