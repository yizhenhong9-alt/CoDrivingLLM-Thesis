"""M22-R3 single seed0 episode, original mutable memory, isolated fresh store."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.accept_memory_live_step import main, require
from llm_controller.local_memory import canonical, text_hash


def validate_episode(outer, episode, steps, *, expected_seed=0, initial_records=None, test_only=True):
    require(outer['traffic_exit_code'] == 0 and outer['status'] == 'project_episode_terminal' and
            episode['status'] == 'episode_terminal', 'Episode did not terminate naturally; retain partial results')
    shutdown = outer['shutdown']
    require(shutdown['exit_code'] == 0 and shutdown['clean_observation'] is True and
            shutdown['port_closed'] is True and shutdown['remaining_known_processes'] == [] and
            shutdown['warnings'] == [], 'Qwen shutdown requires review')
    require(episode['seed'] == expected_seed and episode['memory_mode'] == 'on' and
            episode['memory_module_imported'] is False and
            episode['actual_environment_steps'] == len(steps) and 1 <= len(steps) <= 300,
            'Episode scope mismatch')
    session = episode['memory_session']
    require(session['opened'] is True and session['closed'] is True and
            session['final_snapshot_verified'] is True and session['initial_count'] == len(initial_records or {}),
            'Memory lifecycle mismatch')
    previous, known = session['initial_snapshot_sha256'], dict(initial_records or {})
    initial_count = len(known)
    for index, step in enumerate(steps):
        require(step['step_id'] == index and step['status'] == 'single_step_complete' and
                step['actual_environment_steps'] == index+1 and step['mode'] == 'live' and
                step['done'] is (index == len(steps)-1), 'Step sequence/terminal mismatch')
        queries, events, calls = step['memory_queries'], step['memory_updates'], step['calls']
        require(len(queries) == len(events) == 4 and len(calls) == 5, 'Expected four CAVs and five calls')
        for call in calls:
            require(call['sent_to_model'] is True and call['parsers']['strict']['status'] == 'parsed' and
                    call['token_budget']['input_tokens']+256 <= 2048, 'Live reply/parser/budget mismatch')
        for query, event, call in zip(queries, events, calls[1:]):
            count = len(known)
            require(query['corpus_count'] == event['count_before'] == count and
                    event['count_after'] == count+1 and event['status'] == 'verified' and
                    query['snapshot_sha256'] == event['snapshot_before'] == previous and
                    query['candidate_count'] == min(2, count), 'Rolling corpus sequence mismatch')
            for hit in query['candidates']:
                require(hit['id'] in known and hit['text'] == known[hit['id']]['text'] and
                        hit['metadata'] == known[hit['id']]['metadata'], 'Retrieved source mismatch')
            meta, receipt = event['metadata'], event['write_receipt']
            require(meta['human_question'] == meta['negotiation_result'] == 'None' and
                    meta['final_action'] == str([call['parsers']['strict']['value']['action_id']]) and
                    meta['source']['test_only'] is test_only and meta['source']['step_id'] == index and
                    meta['source']['method'] == 'original-per-vehicle-pre-step' and event['id'] not in known and
                    receipt['id'] == event['id'] and receipt['text_sha256'] == text_hash(event['text']) and
                    receipt['metadata_sha256'] == text_hash(canonical(meta)), 'Write payload/receipt mismatch')
            known[event['id']], previous = event, event['snapshot_after']
    require(len(known)-initial_count == session['queries'] == session['writes'] and
            len(known) == session['final_count'] and
            previous == session['final_snapshot_sha256'], 'Final rolling corpus mismatch')


if __name__ == '__main__':
    main(_episode=True)
