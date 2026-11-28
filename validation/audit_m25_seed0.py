"""Audit the reviewed M25 seed0 evidence without opening any database."""
import json
from pathlib import Path

from validation.accept_memory_episode import validate_episode


def audit(source):
    source = Path(source)
    managers = list((source/'live').glob('*/result.json'))
    if len(managers) != 1:
        raise ValueError('Exactly one pilot manager required')
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    outer = load(managers[0])
    episodes = list((managers[0].parent/'traffic').glob('*/result.json'))
    if len(episodes) != 1:
        raise ValueError('Exactly one pilot episode required')
    episode = load(episodes[0])
    steps = [load(episodes[0].parent/n) for n in episode['step_files']]
    validate_episode(outer, episode, steps)
    from validation.retain_m25_seed0 import validate_labels
    seen = {}
    for step in steps:
        validate_labels(step)
        for row in step['vehicle_identifiers']:
            key, name = row['simulation_id'], row['legacy_label']
            if key in seen and seen[key] != name:
                raise ValueError('Display label changed during episode')
            seen[key] = name
    session = episode['memory_session']
    return dict(git_commit=episode['git_commit'], steps=len(steps),
                final_count=session['final_count'],
                final_snapshot=session['final_snapshot_sha256'],
                test_only=session['test_only'])
