"""Read-only M24 exported episode audit; stdlib only, never opens Chroma."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.accept_memory_episode import validate_episode


def audit(folder):
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    manager_paths = list((folder/'live').glob('*/result.json'))
    assert len(manager_paths) == 1, 'Expected one manager'
    manager_path = manager_paths[0]
    outer = read(manager_path)
    episodes = list((manager_path.parent/'traffic').glob('*/result.json'))
    assert len(episodes) == 1, 'Expected one episode'
    ep_path = episodes[0]
    ep = read(ep_path)
    steps = [read(ep_path.parent/n) for n in ep['step_files']]
    assert len(steps) == len(list(ep_path.parent.glob('step-*.json')))
    validate_episode(outer, ep, steps)  # Actual rolling provenance/snapshot gate, test-only seed0.
    commit = (folder/'git-commit.txt').read_text().strip()
    assert ep['git_commit'] == outer['git_commit'] == commit
    assert ep['git_status'] == '' and (folder/'git-status.txt').read_text().strip() == ''
    assert (folder/'acceptance-exit-code.txt').read_text().strip() == '0'
    budgets, writes, calls = [], [], []
    for step in steps:
        assert step['git_commit'] == commit
        assert step['vehicle_label_version'] == 'M24-simulation-id'
        identifiers = step['vehicle_identifiers']
        ids = [v['simulation_id'] for v in identifiers]
        labels = [v['legacy_label'] for v in identifiers]
        assert len(ids) == len(set(ids)) and len(labels) == len(set(labels))
        for entry in identifiers:
            match = re.fullmatch(r'(MDPVehicle|IDMVehicle) #([0-9]+)', entry['legacy_label'])
            assert match and int(match.group(2)) == entry['simulation_id']
        assert [v['vehicle_id'] for v in step['submitted_vehicle_actions']] == [3, 4, 5, 6]
        assert all(not v['crashed'] for v in step['final_vehicles'])
        assert step['info']['cav_crashed'] is False
        calls.extend(step['calls'])
        budgets.extend(c['token_budget']['input_tokens'] for c in step['calls'])
        writes.extend(step['memory_updates'])
    final = steps[-1]
    threshold = ep['config']['duration'] * ep['config']['policy_frequency'] - 1
    assert ep['actual_environment_steps'] < threshold, 'Cannot rule out environment time limit'
    assert final['done'] and final['info']['agents_dones'] == [True]*4
    hashes = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.rglob('*')) if p.is_file()}
    return dict(status='PASS', source_directory=str(folder), git_commit=commit,
                steps=len(steps), qwen_calls=len(calls), strict_parsed_calls=sum(
                    c['parsers']['strict']['status'] == 'parsed' for c in calls),
                queries=ep['memory_session']['queries'], writes=len(writes),
                initial_count=ep['memory_session']['initial_count'], final_count=ep['memory_session']['final_count'],
                final_snapshot=ep['memory_session']['final_snapshot_sha256'],
                test_only=ep['memory_session']['test_only'],
                max_input_tokens=max(budgets), output_reservation=256,
                max_required_tokens=max(budgets)+256,
                simulated_seconds=sum(s['step_observation']['simulated_seconds'] for s in steps),
                physics_ticks=sum(s['step_observation']['physics_ticks'] for s in steps),
                any_cav_crash=False, final_agents_dones=final['info']['agents_dones'],
                arrival='inferred from unchanged terminal logic: all dones, no crash, below time limit',
                shutdown=outer['shutdown'],
                unique_memory_texts=len(set(e['text'] for e in writes)),
                memory_text_frequency=Counter(e['text'] for e in writes).most_common(),
                source_sha256=hashes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.folder.resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in
                     ('source_sha256', 'memory_text_frequency')}, indent=2, ensure_ascii=False))
