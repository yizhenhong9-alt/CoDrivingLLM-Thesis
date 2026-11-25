"""M20-R5 install guards; ML imports occur only in explicit Spark --phase runtime."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import personal_path
from validation.plan_minilm_runtime import freeze_map

CPU_URL = ('https://download-r2.pytorch.org/whl/cpu/'
           'torch-2.9.1%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl'
           '#sha256=3bf9b442a51a2948e41216a76d7ab00f0694cfcaaa51b6f9bcab57b7f89843e6')
ADDITIONS = {'jinja2': '3.1.6', 'markupsafe': '3.0.4', 'mpmath': '1.3.0',
             'networkx': '3.7', 'regex': '2026.11.23', 'safetensors': '0.8.0',
             'sympy': '1.14.0', 'torch': '2.9.1+cpu', 'transformers': '5.22.2'}


def verify_versions(baseline, current, installed):
    expected = dict(baseline)
    if set(baseline) & set(ADDITIONS):
        raise ValueError('Approved additions unexpectedly exist in baseline')
    if installed:
        expected.update(ADDITIONS)
    if current != expected:
        raise ValueError('Package versions differ from approved baseline/additions')


def approved_requirements():
    return 'torch @ '+CPU_URL+'\n'+''.join('{}=={}\n'.format(k, v)
                                           for k, v in sorted(ADDITIONS.items()) if k != 'torch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--phase', choices=('before', 'after', 'runtime'), required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() != 'aarch64' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Spark ARM64/Python 3.12 only')
    if Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312'):
        raise ValueError('Expected dedicated memory environment')
    personal_path(ROOT)
    personal_path(Path(sys.prefix))
    plan_dir = personal_path(args.plan_dir)
    output = personal_path(args.output_dir)
    plan = json.loads((plan_dir/'plan.json').read_text(encoding='utf-8'))
    if plan.get('cpu_wheel_url') != CPU_URL or plan.get('torch') != ADDITIONS['torch'] or plan.get('transformers') != ADDITIONS['transformers']:
        raise ValueError('Plan differs from reviewed step4 CPU package selection')
    baseline_path = personal_path(Path(plan['baseline']))
    if hashlib.sha256(baseline_path.read_bytes()).hexdigest() != plan['baseline_sha256']:
        raise ValueError('Verified Chroma baseline file changed')
    baseline = freeze_map(baseline_path.read_text(encoding='utf-8'))
    if freeze_map((plan_dir/'constraints.txt').read_text(encoding='utf-8')) != baseline:
        raise ValueError('Plan constraints do not exactly protect Chroma baseline')
    from validation.plan_minilm_runtime import name_key
    current = {name_key(d.metadata['Name']): d.version for d in importlib.metadata.distributions()}
    verify_versions(baseline, current, args.phase != 'before')
    if args.phase == 'before':
        (output/'install-requirements.txt').write_text(approved_requirements(), encoding='utf-8')
    result = dict(status='PASS', phase=args.phase, packages=current,
                  baseline_preserved=True, model_download=False, model_loaded=False)
    if args.phase == 'runtime':
        import torch
        from transformers import AutoModel, AutoTokenizer, BertModel
        import safetensors
        torch.set_num_threads(1)
        if torch.__version__ != ADDITIONS['torch'] or torch.version.cuda is not None:
            raise ValueError('Expected CPU-only torch build')
        left = torch.tensor([[1., 2.], [3., 4.]], device='cpu')
        product = left @ left
        if not torch.equal(product, torch.tensor([[7., 10.], [15., 22.]])):
            raise ValueError('CPU tensor calculation mismatch')
        result.update(torch=torch.__version__, cuda_build=torch.version.cuda,
                      device=str(product.device), tensor_result=product.tolist(),
                      imports=['AutoModel', 'AutoTokenizer', 'BertModel', 'safetensors'],
                      limitation='Imports/tiny CPU tensor only; no pretrained model instantiated')
    (output/(args.phase+'.json')).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
