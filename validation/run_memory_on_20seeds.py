"""M23: seeds0..19 once, fresh shared original-memory corpus; Spark manual entry."""
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
from validation.memory_service_session import memory_service
from validation.accept_memory_episode import validate_episode


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--recovery-source', type=Path)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and sys.version_info[:2] == (3,8) and
            Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'), 'Existing Spark sim environment required')
    run = personal_path(args.run_dir)
    personal_path(ROOT)
    require(run.is_dir(), 'Fresh run directory required')
    commit = subprocess.run(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'], cwd=str(ROOT),
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git','-c','safe.directory='+ROOT.as_posix(),'status','--porcelain=v1'], cwd=str(ROOT),
                           capture_output=True, text=True, check=True).stdout.strip()
    require(not dirty, 'Clean committed checkout required; preserve edits and stop')
    report = dict(format='m23-original-memory-batch-v1', status='initializing', git_commit=commit,
                  seeds=list(range(20)), memory='on', initial_corpus='fresh-empty',
                  corpus_policy='shared-in-seed-order-original-per-vehicle-pre-step',
                  max_steps=300, wall_seconds=3600, episodes=[])
    save = lambda: (run/'batch-result.json').write_text(canonical(report)+'\n', encoding='utf-8')
    save()
    baseline = json.loads((ROOT/'validation/memory_on_baseline_contract.json').read_text(encoding='utf-8'))
    report['baseline_contract'] = baseline
    save()
    known = {}
    recovery = None
    if args.recovery_source is not None:
        from validation.recover_memory_batch import load_evidence
        source=personal_path(args.recovery_source)
        recovery=json.loads((run/'recovery.json').read_text(encoding='utf-8'))
        require(recovery['status']=='ready' and recovery['source']==str(source) and recovery['source_unchanged'] is True,
                'Verified prepared recovery required')
        old,known,removed,unused=load_evidence(source)
        report.update(initial_corpus='recovered-seed0-boundary',recovery=recovery,
                      resumed_seeds=list(range(1,20)))
        first=dict(old['episodes'][0],retained_from_commit=old['git_commit'],attempt='retained-original-seed0')
        report['episodes'].append(first)
        save()
    database, spec = personal_path(run/'experiment-chroma'), manifest(QUERY_SCHEMA)
    client = MemoryHTTPClient(spec, 18082)
    try:
        with memory_service(run/'service', database, spec, 18082, create=recovery is None,
                            writable=recovery is not None, qwen_tokenizer=True):
            initial=client.status()
            require(initial['count']==len(known),'Initial corpus count differs from evidence')
            if recovery is not None:
                require(initial['snapshot_sha256']==recovery['restored_snapshot'],'Recovered snapshot mismatch')
            config = dict(format='m22-original-v1', manifest=spec, port=18082, timeout=30,
                store_path_sha256=text_hash(database.as_posix()), context_limit=2048, output_tokens=256, test_only=False)
            cfg = run/'memory-config.json'
            cfg.write_text(canonical(config)+'\n', encoding='utf-8')
            previous = client.status()['snapshot_sha256']
            for seed in (report['seeds'] if recovery is None else report['resumed_seeds']):
                phase = run/('seed-{:02d}'.format(seed))
                phase.mkdir()
                row = dict(seed=seed, status='running', initial_count=len(known), initial_snapshot_sha256=previous)
                row['attempt']='retry-after-retrieval-fix' if recovery is not None and seed==1 else 'first-attempt'
                report['episodes'].append(row)
                report['status'] = 'running'
                save()
                command = ['/home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python','-B',
                    str(ROOT/'validation/run_qwen_live_session.py'),'--output-dir',str(phase/'live'),
                    '--project-entry','--seed',str(seed),'--max-steps','300','--wall-seconds','3600',
                    '--memory','on','--memory-config',str(cfg)]
                with (phase/'console.txt').open('x', encoding='utf-8') as output:
                    code = subprocess.run(command, cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT).returncode
                row['manager_exit_code'] = code
                save()
                require(code == 0, 'Seed {} failed; stop batch, retain partial writes; no automatic retry'.format(seed))
                managers = list((phase/'live').glob('*/result.json'))
                require(len(managers) == 1, 'One manager report required')
                outer = json.loads(managers[0].read_text(encoding='utf-8'))
                ep_path = personal_path(Path(outer['traffic_report']))
                ep = json.loads(ep_path.read_text(encoding='utf-8'))
                require(ep['config'] == baseline['config'] and ep['model'] == baseline['model'] and
                        ep['parser_mode'] == baseline['parser'] and ep['settings']['max_steps'] == baseline['max_steps'] and
                        ep['settings']['wall_seconds'] == baseline['wall_seconds'], 'Baseline environment/model settings mismatch')
                steps = [json.loads(personal_path(ep_path.parent/n).read_text(encoding='utf-8')) for n in ep['step_files']]
                require(ep['git_commit'] == outer['git_commit'] == commit and ep['git_status'] == '', 'Source changed during batch')
                require(ep['memory_session']['initial_snapshot_sha256'] == previous, 'Cross-episode snapshot mismatch')
                validate_episode(outer, ep, steps, expected_seed=seed, initial_records=known, test_only=False)
                for step in steps:
                    for event in step['memory_updates']:
                        known[event['id']] = event
                status = client.status()
                previous = ep['memory_session']['final_snapshot_sha256']
                require(status['count'] == len(known) and status['snapshot_sha256'] == previous, 'Final service corpus mismatch')
                collision = any(s['info']['cav_crashed'] or any(v['crashed'] for v in s['final_vehicles']) for s in steps)
                final = steps[-1]
                timed_out = ep['actual_environment_steps'] >= ep['config']['duration']*ep['config']['policy_frequency']-1
                outcome = ('cav_collision' if collision else 'all_arrived_inferred' if
                    not timed_out and all(final['info']['agents_dones']) else 'environment_time_limit' if timed_out else 'other_terminal')
                row.update(status='verified', manager_report=str(managers[0]), episode_report=str(ep_path),
                    steps=len(steps), final_count=len(known), final_snapshot_sha256=previous, outcome=outcome,
                    simulated_seconds=sum(s['step_observation']['simulated_seconds'] for s in steps))
                save()
                print('M23 seed {} verified; steps={}; outcome={}; corpus={}'.format(seed,len(steps),outcome,len(known)), flush=True)
        report.update(status='completed', final_count=len(known), final_snapshot_sha256=previous)
        save()
        print('M23 memory-on 20 seeds completed; retain raw results for paired audit', flush=True)
    except BaseException as error:
        report.update(status='stopped_requires_review', error_type=type(error).__name__, error=str(error))
        save()
        raise


if __name__ == '__main__':
    main()
