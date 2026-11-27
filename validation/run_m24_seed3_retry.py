"""ONE explicit unchanged-prompt seed3 retry from a prepared 800-record copy."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from llm_controller.local_memory import canonical, manifest, personal_path, text_hash
from llm_controller.memory_http import MemoryHTTPClient
from llm_controller.memory_prompt import QUERY_SCHEMA
from validation.accept_memory_episode import validate_episode
from validation.memory_service_session import memory_service
from validation.recover_m24_seed3 import load_prepared, AFTER, require
from validation.retain_m24_seed0 import validate_labels


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    require(sys.platform=='linux' and platform.machine()=='aarch64' and sys.version_info[:2]==(3,8) and
            Path(sys.prefix)==Path('/home/nclab/Yizhen/envs/codriving-sim-py38'),
            'Existing Spark sim environment required')
    run=personal_path(args.run_dir); personal_path(ROOT)
    require(run.is_dir() and not (run/'retry-result.json').exists() and not (run/'retry-started.json').exists(),
            'Only one retry allowed per prepared copy; existing attempts must be preserved')
    source=personal_path(Path('/home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-PvMXov'))
    old,known,recovery=load_prepared(source,run)
    git=['git','-c','safe.directory='+ROOT.as_posix()]
    commit=subprocess.run(git+['rev-parse','HEAD'],cwd=str(ROOT),capture_output=True,text=True,check=True).stdout.strip()
    dirty=subprocess.run(git+['status','--porcelain=v1'],cwd=str(ROOT),capture_output=True,text=True,check=True).stdout.strip()
    require(not dirty,'Clean committed checkout required; preserve other edits and stop')
    baseline=old['baseline_contract']
    report=dict(format='m24-seed3-single-retry-v1',status='initializing',seed=3,attempt=2,
        scope='one retry only; seeds4-19 NOT launched',source=str(source),source_commit=old['git_commit'],
        git_commit=commit,initial_count=800,initial_snapshot_sha256=AFTER,
        recovery=recovery,prompt_changed=False,strict_changed=False)
    save=lambda: (run/'retry-result.json').write_text(canonical(report)+'\n',encoding='utf-8')
    # Atomic evidence marker, before starting any service. No automatic in-place retries.
    with (run/'retry-started.json').open('x',encoding='utf-8') as stream:
        stream.write(canonical(dict(seed=3,attempt=2,git_commit=commit))+'\n')
    save()
    database=personal_path(run/'experiment-chroma'); spec=manifest(QUERY_SCHEMA)
    client=MemoryHTTPClient(spec,18082)
    try:
        with memory_service(run/'service',database,spec,18082,writable=True,qwen_tokenizer=True):
            try:
                status=client.status()
                require(status['count']==800 and status['snapshot_sha256']==AFTER,'Initial 800 boundary mismatch')
                config=dict(format='m22-original-v1',manifest=spec,port=18082,timeout=30,
                    store_path_sha256=text_hash(database.as_posix()),context_limit=2048,output_tokens=256,test_only=False)
                cfg=run/'memory-config.json'; cfg.write_text(canonical(config)+'\n',encoding='utf-8')
                phase=run/'seed-03'; phase.mkdir()
                command=['/home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python','-B',
                    str(ROOT/'validation/run_qwen_live_session.py'),'--output-dir',str(phase/'live'),
                    '--project-entry','--seed','3','--max-steps','300','--wall-seconds','3600',
                    '--memory','on','--memory-config',str(cfg)]
                report['status']='running'; save()
                print('Starting ONE seed3 retry from 800 records; unchanged prompt/strict; no later seeds',flush=True)
                with (phase/'console.txt').open('x',encoding='utf-8') as output:
                    code=subprocess.run(command,cwd=str(ROOT),stdout=output,stderr=subprocess.STDOUT).returncode
                report['manager_exit_code']=code; save()
                require(code==0,'Seed3 retry failed; preserve partial writes and stop; NO further retry')
                paths=list((phase/'live').glob('*/result.json'))
                require(len(paths)==1,'One manager report required')
                manager=json.loads(paths[0].read_text(encoding='utf-8'))
                ep_path=personal_path(Path(manager['traffic_report'])); ep_path.relative_to(run)
                ep=json.loads(ep_path.read_text(encoding='utf-8'))
                require(ep['git_commit']==manager['git_commit']==commit and ep['git_status']=='',
                        'Decision source changed during retry')
                require(ep['config']==baseline['config'] and ep['model']==baseline['model'] and
                        ep['parser_mode']==baseline['parser'] and ep['settings']['max_steps']==300 and
                        ep['settings']['wall_seconds']==3600,'Original experiment contract mismatch')
                require(ep['memory_session']['initial_snapshot_sha256']==AFTER,'Episode did not start at800')
                steps=[json.loads((ep_path.parent/name).read_text(encoding='utf-8')) for name in ep['step_files']]
                validate_episode(manager,ep,steps,expected_seed=3,initial_records=known,test_only=False)
                for step in steps:
                    validate_labels(step)
                    for event in step['memory_updates']: known[event['id']]=event
                status=client.status()
                require(status['count']==len(known) and status['snapshot_sha256']==ep['memory_session']['final_snapshot_sha256'],
                        'Final retry corpus mismatch')
                collision=any(s['info']['cav_crashed'] or any(v['crashed'] for v in s['final_vehicles']) for s in steps)
                timed_out=ep['actual_environment_steps']>=ep['config']['duration']*ep['config']['policy_frequency']-1
                outcome=('cav_collision' if collision else 'environment_time_limit' if timed_out else
                         'all_arrived_inferred' if all(steps[-1]['info']['agents_dones']) else 'other_terminal')
                report.update(status='verified',steps=len(steps),outcome=outcome,
                    manager_report=str(paths[0]),episode_report=str(ep_path),
                    simulated_seconds=sum(s['step_observation']['simulated_seconds'] for s in steps))
                save()
            finally:
                try:
                    status=client.status()
                    report.update(final_count=status['count'],final_snapshot_sha256=status['snapshot_sha256'])
                except Exception as error:
                    report['final_observation_error']=str(error)
                save()
        report['memory_service_closed']=True; save()
        print('Seed3 retry verified; outcome={}; NO seeds4-19 started'.format(report['outcome']),flush=True)
    except BaseException as error:
        report.update(status='stopped_requires_review',error_type=type(error).__name__,error=str(error)); save()
        raise


if __name__=='__main__':
    main()
