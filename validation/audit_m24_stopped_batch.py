"""Audit exported M24 seed3 negotiation failure, without DB/model/network access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, text_hash
from llm_controller.output_schema import OutputValidationError, parse_negotiation
from validation.accept_memory_episode import validate_episode
from validation.retain_m24_seed0 import load_evidence, validate_labels


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def audit(folder):
    folder = folder.resolve()
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    checked = 0
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        file = (folder/name).resolve()
        file.relative_to(folder)
        require(hashlib.sha256(file.read_bytes()).hexdigest() == digest, 'Export hash mismatch: '+name)
        checked += 1
    batch = read(folder/'batch-result.json')
    require(batch['status'] == 'stopped_requires_review' and len(batch['episodes']) == 4,
            'Unexpected stopped batch scope')
    require(not list(folder.glob('seed-0[4-9]')) and not list(folder.glob('seed-1?')), 'Later seeds exist')
    pilot, known = load_evidence(folder/'retained-seed0')
    previous = pilot['memory_session']['final_snapshot_sha256']
    rows, all_calls = [], []
    retained800, failed_ids = None, []
    for seed in (1, 2, 3):
        path = next((folder/('seed-{:02d}'.format(seed))/'live').glob('*/result.json'))
        manager = read(path)
        ep_path = next((path.parent/'traffic').glob('*/result.json'))
        episode = read(ep_path)
        steps = [read(ep_path.parent/n) for n in episode['step_files']]
        require(episode['git_commit'] == manager['git_commit'] == batch['git_commit'] and
                episode['git_status'] == '', 'Unexpected decision source/dirty checkout')
        shutdown = manager['shutdown']
        require(shutdown['exit_code'] == 0 and shutdown['port_closed'] is True and
                shutdown['clean_observation'] is True and shutdown['warnings'] == [] and
                shutdown['remaining_known_processes'] == [], 'Shutdown requires review')
        require(episode['memory_session']['initial_count'] == len(known) and
                episode['memory_session']['initial_snapshot_sha256'] == previous, 'Initial corpus mismatch')
        initial_count = len(known)
        if seed < 3:
            validate_episode(manager, episode, steps, expected_seed=seed, initial_records=known, test_only=False)
        else:
            retained800 = set(known)
            require(initial_count == 800 and len(steps) == 16 and episode['actual_environment_steps'] == 15,
                    'Unexpected failure boundary')
        for index, step in enumerate(steps):
            all_calls.extend(step['calls'])
            if seed == 3 and index == 15:
                failure = step
                break
            validate_labels(step)
            require(step['step_id'] == index and step['status'] == 'single_step_complete' and
                    step['actual_environment_steps'] == index+1, 'Step sequence mismatch')
            queries, updates, calls = step['memory_queries'], step['memory_updates'], step['calls']
            require(len(queries) == len(updates) == 4 and len(calls) == 5, 'Completed step shape mismatch')
            require(all(c['sent_to_model'] and c['parsers']['strict']['status'] == 'parsed' and
                        c['token_budget']['input_tokens']+256 <= 2048 for c in calls), 'Completed reply mismatch')
            for query, event, call in zip(queries, updates, calls[1:]):
                require(query['snapshot_sha256'] == event['snapshot_before'] == previous and
                        query['corpus_count'] == event['count_before'] == len(known) and
                        event['count_after'] == len(known)+1 and event['status'] == 'verified' and
                        query['candidate_count'] == min(2, len(known)), 'Rolling corpus mismatch')
                for hit in query['candidates']:
                    require(hit['id'] in known and hit['text'] == known[hit['id']]['text'] and
                            hit['metadata'] == known[hit['id']]['metadata'], 'Candidate provenance mismatch')
                meta, receipt = event['metadata'], event['write_receipt']
                require(event['id'] not in known and meta['source']['test_only'] is False and
                        meta['source']['step_id'] == index and meta['human_question'] == meta['negotiation_result'] == 'None' and
                        meta['final_action'] == str([call['parsers']['strict']['value']['action_id']]) and
                        receipt['id'] == event['id'] and receipt['text_sha256'] == text_hash(event['text']) and
                        receipt['metadata_sha256'] == text_hash(canonical(meta)), 'Write payload mismatch')
                known[event['id']] = event
                previous = event['snapshot_after']
                if seed == 3:
                    failed_ids.append(event['id'])
        session = episode['memory_session']
        require(session['closed'] is True and session['final_snapshot_verified'] is True and
                session['final_count'] == len(known) and session['final_snapshot_sha256'] == previous and
                session['queries'] == session['writes'] == len(known)-initial_count, 'Final corpus mismatch')
        successful = steps if seed < 3 else steps[:-1]
        crashed = sorted({v['vehicle_id'] for s in successful for v in s['final_vehicles'] if v['crashed']})
        rows.append(dict(seed=seed, status=episode['status'], steps=episode['actual_environment_steps'],
            calls=sum(len(s['calls']) for s in steps), initial_count=initial_count, final_count=len(known),
            simulated_seconds=sum(s['step_observation']['simulated_seconds'] for s in successful),
            cav_crashed_ids=crashed, snapshot=previous, shutdown=shutdown))
    require(len(known) == 860 and len(retained800) == 800 and len(failed_ids) == len(set(failed_ids)) == 60 and
            not retained800.intersection(failed_ids), '800 retained / 60 partial ID separation failed')
    require(failure['status'] == 'failed' and len(failure['calls']) == 1 and
            failure['calls'][0]['stage'] == 'negotiation' and failure['memory_queries'] == [] and
            failure['memory_updates'] == [] and not failure.get('step_attempted'), 'Failed step side effects')
    call = failure['calls'][0]
    pairs, raw = call['context']['pairs'], call['raw_response']
    require(pairs == [[3, 2], [4, 3]], 'Unexpected conflict pairs')
    try:
        parse_negotiation(raw, pairs)
    except OutputValidationError as error:
        require(str(error) == 'Missing conflict decisions', 'Different parser failure')
    else:
        raise ValueError('Expected parser rejection')
    usage = call['api_response']['usage']
    return dict(status='PASS', export_files_verified=checked, batch_commit=batch['git_commit'],
        seeds=rows, total_new_calls=len(all_calls), final_count=860, failed_step=15,
        expected_pairs=pairs, raw_response=raw,
        prompt_tokens=usage['prompt_tokens'], completion_tokens=usage['completion_tokens'],
        finish_reason=call['api_response']['choices'][0]['finish_reason'],
        response_matches_fixed_example=('Return only JSON: '+raw+'.') in call['messages'][0]['content'],
        retained_boundary_count=800, retained_boundary_snapshot=rows[1]['snapshot'],
        failed_final_snapshot=rows[2]['snapshot'], partial_ids=failed_ids,
        limitation='Read-only exported provenance/receipt audit; no database reopened or restored. Example copying is a hypothesis, not a proven cause.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    result=audit(args.folder)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='partial_ids'},indent=2,ensure_ascii=False))
