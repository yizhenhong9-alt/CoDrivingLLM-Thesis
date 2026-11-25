"""Audit returned Spark M21-R1 evidence against local saved M16; stdlib only."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from llm_controller.memory_prompt import original_experience, original_query, INTRO, MARKER
from llm_controller.local_memory import text_hash
from llm_controller.qwen_step import MODEL


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    folder = ROOT.parent/'runs/m21-1'
    evidence = folder/'acceptance.json'
    result = json.loads(evidence.read_text(encoding='utf-8'))
    commit = (folder/'git-commit.txt').read_text(encoding='utf-8').strip()
    require(commit == 'e0dd0eba8b192c1501b9e144aa16913d67ca4e92', 'Unexpected commit')
    require(result['status'] == 'PASS' and result['model'] == MODEL, 'Model/status mismatch')
    fixture = ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json'
    require(result['fixture_sha256'] == text_hash(fixture.read_text(encoding='utf-8')), 'Fixture hash mismatch')
    rows = json.loads(fixture.read_text(encoding='utf-8'))['rows']
    hits = [dict(metadata=row['would_write']['metadata']) for row in rows]
    sources = list((ROOT.parent/'runs/M16-one-episode').rglob('step-*.json'))
    by_name = {}
    for path in sources:
        by_name.setdefault(path.name, []).append(path)
    seen = set()
    verified_files = {}
    token_counts = []
    candidates, injected, excluded = Counter(), Counter(), Counter()
    for record in result['records']:
        name = Path(record['step_file']).name
        require(len(by_name.get(name, [])) == 1, 'Ambiguous/missing local M16 '+name)
        path = by_name[name][0]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == record['step_sha256'], 'M16 source hash mismatch '+name)
        verified_files[name] = digest
        step = json.loads(raw)
        index = record['call_index']
        key = (name, index)
        require(key not in seen, 'Duplicate action record')
        seen.add(key)
        call = step['calls'][index]
        require(call['stage'] == 'action' and call['context']['vehicle_id'] == record['vehicle_id'], 'Call mismatch')
        base = call['messages'][0]['content']
        require(text_hash(base) == record['base_prompt_sha256'], 'Base prompt changed')
        size = record['injected_count']
        require(type(size) is int and 0 <= size <= 2, 'Invalid injection count')
        section = '\n'+INTRO+original_experience(hits[:size])+'\n'
        expected = base.replace(MARKER, section+MARKER, 1)
        require(record['messages'] == [dict(role='system', content=expected)], 'Injected text mismatch')
        require(text_hash(expected) == record['final_prompt_sha256'], 'Final prompt hash mismatch')
        scenario = base.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
        require(text_hash(original_query(scenario)) == record['query_sha256'], 'Query hash mismatch')
        require(record['candidate_count'] == 2 and record['excluded_count'] == 2-size, 'Count mismatch')
        require(record['output_tokens'] == 256 and record['context_limit'] == 2048, 'Budget changed')
        attempts = record['attempts']
        require([a['memory_count'] for a in attempts] == list(range(2, size-1, -1)), 'Attempt order mismatch')
        for attempt in attempts:
            require(type(attempt['input_tokens']) is int and attempt['input_tokens'] > 0 and
                    attempt['required_tokens'] == attempt['input_tokens']+256, 'Bad token arithmetic')
        require(all(a['required_tokens'] > 2048 for a in attempts[:-1]), 'Unnecessary exclusion')
        require(attempts[-1]['input_tokens'] == record['input_tokens'] and
                record['input_tokens']+256 <= 2048, 'Final budget mismatch')
        require(record['exclusion_reason'] == ('token_budget' if size < 2 else None), 'Reason mismatch')
        token_counts.append(record['input_tokens'])
        candidates[record['candidate_count']] += 1
        injected[size] += 1
        excluded[record['excluded_count']] += 1
    expected_keys = {(name, index) for name in verified_files
                     for index, call in enumerate(json.loads(by_name[name][0].read_bytes())['calls'])
                     if call['stage'] == 'action'}
    require(seen == expected_keys and len(seen) == result['action_count'] == 404 and
            len(verified_files) == 101, 'Incomplete source coverage')
    audit = dict(status='PASS', verified_commit=commit, action_count=len(seen),
                 step_count=len(verified_files), candidate_counts=dict(candidates),
                 injected_counts=dict(injected), excluded_counts=dict(excluded),
                 min_input_tokens=min(token_counts), max_input_tokens=max(token_counts),
                 output_tokens=256, context_limit=2048,
                 maximum_required_tokens=max(token_counts)+256,
                 minimum_remaining_tokens=2048-max(token_counts)-256,
                 evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
                 commit_file_sha256=hashlib.sha256((folder/'git-commit.txt').read_bytes()).hexdigest(),
                 fixture_sha256=result['fixture_sha256'], verified_step_sha256=verified_files,
                 limitation='Validates returned counts and exact messages/hashes against local M16; does not independently rerun the real tokenizer, retrieval or Qwen generation.')
    (Path(__file__).parent/'spark-audit.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in audit.items() if k != 'verified_step_sha256'}, indent=2))


if __name__ == '__main__':
    main()
