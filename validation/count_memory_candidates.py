"""M21-R2 offline Qwen tokenizer worker. No model weights or HTTP calls."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, personal_path, text_hash
from llm_controller.memory_prompt import fit_prompt


def count_candidates(cases, tokenizer):
    counts = {}
    for case in cases:
        def count(messages):
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            ids = tokenizer.encode(rendered, add_special_tokens=False)
            if not isinstance(ids, list) or any(type(item) is not int for item in ids):
                raise ValueError('Expected flat tokenizer IDs')
            digest = text_hash(canonical(messages))
            if digest in counts and counts[digest] != len(ids):
                raise ValueError('Inconsistent tokenizer output')
            counts[digest] = len(ids)
            return len(ids)
        # Ask for each complete candidate prefix; no estimate or truncation.
        for size in range(len(case['hits']), -1, -1):
            fit_prompt(case['base_prompt'], case['hits'][:size], count,
                       output_tokens=256, context_limit=2048)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != 'linux' or platform.machine() != 'aarch64' or
            Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/qwen-vllm034-py312')):
        raise RuntimeError('Existing Spark Qwen environment required')
    cases_path, output = personal_path(args.cases), personal_path(args.output)
    for key in ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'TRANSFORMERS_CACHE',
                'XDG_CACHE_HOME', 'TMPDIR', 'TMP', 'TEMP'):
        target = personal_path(output.parent/key.lower())
        target.mkdir(exist_ok=True)
        os.environ[key] = str(target)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='',
                      TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1')
    raw = cases_path.read_bytes()
    model = personal_path(Path('/home/nclab/Yizhen/models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4'))
    for path in model.rglob('*'):
        personal_path(path)
    from unittest.mock import patch
    def block(*args, **kwargs):
        raise RuntimeError('Offline tokenizer: network disabled')
    with patch('socket.socket.connect', block), patch('socket.socket.connect_ex', block):
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
        counts = count_candidates(json.loads(raw), tokenizer)
    result = dict(status='PASS', cases_sha256=text_hash(raw.decode('utf-8')), counts=counts,
                  tokenizer_path=str(model), expected_revision='5a5a776300a41aaa681dd7ff0106608ef2bc90db',
                  limitation='Existing approved tokenizer; no model weights loaded/reverified')
    with output.open('x', encoding='utf-8') as stream:
        stream.write(canonical(result)+'\n')


if __name__ == '__main__':
    main()
