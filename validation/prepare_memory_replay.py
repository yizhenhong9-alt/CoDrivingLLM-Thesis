"""M21-R3 pin accepted R2 evidence and recheck exact prompts with local tokenizer."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import canonical, personal_path, text_hash
from llm_controller.memory_replay import load_config, require
from llm_controller.qwen_step import MODEL
from validation.memory_service_session import offline_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux' and Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/qwen-vllm034-py312'),
            'Existing Spark Qwen environment required')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    require(run.is_dir(), 'Existing fresh run required')
    source = personal_path(Path('/home/nclab/Yizhen/runs/M21-R2-retrieval-prompt-6fIklV'))
    artifacts = {}
    for name, filename, digest in (
            ('acceptance', 'acceptance.json', '28d4167ad41e4a2896ea579bab24c1dd646f188d251ad08afee455d222f0dfc2'),
            ('counts', 'tokenizer/counts.json', 'd92eebc7e42000990ffbf752084dc10d0c0c7f7521b75d48c7fc2e24cdaeb085'),
            ('commit', 'git-commit.txt', '6d4995efaed516ad27281dd8039184877e766fd8b7f1f463e3ed429d870a4d5b')):
        path = personal_path(source/filename)
        require(text_hash(path.read_bytes().decode('utf-8')) == digest, 'Accepted R2 file changed: '+name)
        artifacts[name] = dict(path=str(path), sha256=digest)
    config = dict(format='m21-r3-frozen-retrieval-v1', model=MODEL, context_limit=2048,
                  output_tokens=256, artifacts=artifacts)
    config_path = run/'replay-config.json'
    with config_path.open('x', encoding='utf-8') as stream:
        stream.write(canonical(config)+'\n')
    bundle = load_config(config_path)
    tokenizer_dir = personal_path(run/'tokenizer-check')
    tokenizer_dir.mkdir()
    os.environ.update(offline_env(tokenizer_dir))
    model = personal_path(Path('/home/nclab/Yizhen/models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4'))
    for path in model.rglob('*'):
        personal_path(path)
    from unittest.mock import patch
    def block(*args, **kwargs):
        raise RuntimeError('Offline tokenizer preflight')
    with patch('socket.socket.connect', block), patch('socket.socket.connect_ex', block):
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
        counts = []
        for case in bundle['cases']:
            rendered = tokenizer.apply_chat_template(case['messages'], tokenize=False, add_generation_prompt=True)
            ids = tokenizer.encode(rendered, add_special_tokens=False)
            require(isinstance(ids, list) and all(type(item) is int for item in ids) and
                    len(ids) == case['input_tokens'] and len(ids)+256 <= 2048,
                    'Fresh tokenizer count differs from accepted memory prompt')
            counts.append(len(ids))
    (run/'preflight.json').write_text(canonical(dict(status='PASS', input_tokens=counts,
        config_sha256=bundle['config_sha256'], expected_revision='5a5a776300a41aaa681dd7ff0106608ef2bc90db',
        scope='Local tokenizer only, model weights not loaded; frozen accepted R2 prompts'))+'\n', encoding='utf-8')
    print('M21-R3 tokenizer preflight: PASS; counts='+str(counts))


if __name__ == '__main__':
    main()
