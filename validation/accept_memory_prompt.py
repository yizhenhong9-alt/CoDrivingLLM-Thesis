"""M21-R1 Spark tokenizer-only replay of SAVED prompts with synthetic candidates.

No Qwen generation, simulator, live retrieval, writes, model weights or network.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import personal_path, text_hash, canonical
from llm_controller.memory_prompt import fit_prompt, original_query, INTRO, original_experience
from llm_controller.qwen_step import MODEL


def replay(tokenizer, step_files, output_tokens=256, context_limit=2048):
    fixture_path = ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json'
    fixtures = json.loads(fixture_path.read_text(encoding='utf-8'))['rows']
    hits = [dict(id='synthetic-fixture-'+str(i), text=row['would_write']['page_content'],
                 metadata=dict(row['would_write']['metadata'], source={'test_only': True}),
                 distance=None, score=None) for i, row in enumerate(fixtures)]
    def count(messages):
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        tokens = tokenizer.encode(rendered, add_special_tokens=False)
        if not isinstance(tokens, list) or any(type(value) is not int for value in tokens):
            raise ValueError('Flat tokenizer IDs required')
        return len(tokens)
    records = []
    for file in step_files:
        raw = file.read_bytes()
        step = json.loads(raw)
        if step.get('model') != MODEL or step.get('memory_mode') != 'off':
            raise ValueError('Only saved specified-Qwen memory-off prompts accepted')
        for index, call in enumerate(step['calls']):
            if call['stage'] != 'action':
                continue
            messages = call['messages']
            if len(messages) != 1 or messages[0]['role'] != 'system':
                raise ValueError('Expected original single-system prompt')
            base = messages[0]['content']
            start, end = '\nCurrent scenario:\n', '\nRules:\n'
            if base.count(start) != 1 or base.count(end) != 1:
                raise ValueError('Cannot identify saved scenario boundaries')
            scenario = base.split(start, 1)[1].split(end, 1)[0]
            prompt, receipt = fit_prompt(base, hits, count, output_tokens=output_tokens,
                                         context_limit=context_limit)
            size = receipt['injected_count']
            section = '\n'+INTRO+original_experience(hits[:size])+'\n'
            if prompt.replace(section, '', 1) != base:
                raise ValueError('Existing prompt text changed')
            records.append(dict(step_file=str(file), step_sha256=text_hash(raw.decode('utf-8')),
                                call_index=index, vehicle_id=call['context']['vehicle_id'],
                                query_sha256=text_hash(original_query(scenario)),
                                messages=[{'role': 'system', 'content': prompt}], **receipt))
    if not records:
        raise ValueError('No saved action prompts found')
    return dict(status='PASS', records=records, action_count=len(records),
                fixture_sha256=text_hash(fixture_path.read_text(encoding='utf-8')),
                limitation='Synthetic fixed two-candidate order, not actual retrieval. Tokenizer-only saved-off replay; no traffic or production on validation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step-dir', type=Path)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != 'linux' or platform.machine() != 'aarch64' or
            Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/qwen-vllm034-py312')):
        raise RuntimeError('Use existing Spark Qwen environment; no Windows tokenizer loading')
    personal_path(ROOT)
    if args.step_dir is None:
        candidates = sorted({path.parent for path in personal_path(
            Path('/home/nclab/Yizhen/runs/M16-one-episode')).rglob('step-0000.json')})
        if len(candidates) != 1:
            raise ValueError('Expected one saved M16 step directory; supply --step-dir explicitly')
        args.step_dir = candidates[0]
    steps = personal_path(args.step_dir)
    run = personal_path(args.run_dir)
    if not steps.is_dir() or not run.is_dir():
        raise ValueError('Existing saved step directory and fresh run required')
    files = sorted(personal_path(path) for path in steps.glob('step-*.json'))
    for key in ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'TRANSFORMERS_CACHE',
                'XDG_CACHE_HOME', 'TMPDIR', 'TMP', 'TEMP'):
        target = personal_path(run/key.lower())
        target.mkdir(exist_ok=False)
        os.environ[key] = str(target)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='',
                      TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1')
    model = personal_path(Path('/home/nclab/Yizhen/models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4'))
    for path in model.rglob('*'):
        personal_path(path)
    from unittest.mock import patch
    def no_network(*args, **kwargs):
        raise RuntimeError('Tokenizer replay network disabled')
    with patch('socket.socket.connect', no_network), patch('socket.socket.connect_ex', no_network):
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
        result = replay(tokenizer, files)
    result.update(model=MODEL, tokenizer_path=str(model),
                  expected_revision='5a5a776300a41aaa681dd7ff0106608ef2bc90db',
                  revision_evidence='Existing approved local tokenizer; no weights reverified or loaded')
    with (run/'acceptance.json').open('x', encoding='utf-8') as stream:
        stream.write(canonical(result)+'\n')
    print('M21-R1 tokenizer replay: PASS; action_count={}; max_input_tokens={}'.format(
        result['action_count'], max(row['input_tokens'] for row in result['records'])))


if __name__ == '__main__':
    main()
