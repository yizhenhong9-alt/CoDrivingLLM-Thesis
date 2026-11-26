"""Read-only local Git/evidence audit of legacy vehicle naming across off/on."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT.parent
OFF='21799bdc2abc3b85d1c8562e90827e8287eeaf3d'
ON='add6a861bebebe122fd684ed8578e093d8593103'


def git(*args):
    return subprocess.run(['git','-c','safe.directory='+ROOT.as_posix()]+list(args),cwd=str(ROOT),
                          capture_output=True,check=True).stdout


def main():
    paths=['highway_env/vehicle/kinematics.py','highway_env/envs/common/abstract.py',
           'highway_env/envs/intersection_env.py','llm_controller/llm_agent_action.py',
           'llm_controller/llm_agent_negotiation_system.py','llm_controller/prompt_llm.py',
           'llm_controller/vehicle_actions.py']
    blobs={}
    for path in paths:
        a,b=git('show',OFF+':'+path),git('show',ON+':'+path)
        assert a==b,path
        blobs[path]=hashlib.sha256(a).hexdigest()
    guard='if len(set(names.values())) != len(names):\n        raise OutputValidationError("Original safety-helper labels collided")'
    assert all(guard in git('show',rev+':llm_controller/qwen_step.py').decode() for rev in (OFF,ON))
    load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    off_dir=WORK/'runs/M18-intersection-memory-off-20seeds/seed-01/20261124T012637Z-3235c51c/traffic/20261124T012842Z-92aac95e'
    off_steps=[load(p) for p in sorted(off_dir.glob('step-*.json'))]
    assert len(off_steps)==107
    assert all(len({v['legacy_label'] for v in step['vehicle_identifiers']})==len(step['vehicle_identifiers']) for step in off_steps)
    first_dir=WORK/'runs/M23-review-n2o60wtb/seed-01/live/20261126T014820Z-7edcc0bd/traffic/20261126T015029Z-51c14bf8'
    retry_dirs=list((WORK/'runs/M23-review-6so9070d/seed-01/live').glob('*/traffic/*'))
    assert len(retry_dirs)==1
    first,retry=load(first_dir/'step-0000.json'),load(retry_dirs[0]/'step-0000.json')
    comparisons={}
    for name,step in [('first_on_attempt',first),('recovered_on_attempt',retry)]:
        original={v['vehicle_id']:v for v in off_steps[0]['initial_vehicles']}
        new={v['vehicle_id']:v for v in step['initial_vehicles']}
        assert original.keys()==new.keys()
        comparisons[name]=dict(initial_cav_state_exact_match=original==new,
            max_position_difference=max(abs(a-b) for key in original for a,b in zip(original[key]['position'],new[key]['position'])),
            max_speed_difference=max(abs(original[key]['speed_mps']-new[key]['speed_mps']) for key in original),
            preserved_labels=step.get('vehicle_identifiers'),calls=len(step['calls']),status=step['status'])
    result=dict(status='PASS',off_commit=OFF,on_commit=ON,unchanged_source_blob_sha256=blobs,
        guard_present_in_both=True,off_seed1_steps_with_unique_labels=len(off_steps),comparisons=comparisons,
        off_seed1_initial_labels=off_steps[0]['vehicle_identifiers'],
        introduction=git('log','--oneline','-S','Original safety-helper labels collided','--','llm_controller/qwen_step.py').decode().strip(),
        limitation='Initial snapshots cover four CAVs, not all HDVs; colliding labels were not persisted. Allocation causation is not established.')
    (Path(__file__).parent/'label-history-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='unchanged_source_blob_sha256'},indent=2))


if __name__=='__main__':
    main()
