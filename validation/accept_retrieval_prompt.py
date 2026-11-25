"""M21-R2 Spark 3.8 real HTTP retrieval -> exact tokenizer-budgeted prompt.

Isolated test DB, two original fixtures only; no Qwen generation or traffic.
"""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import manifest, personal_path, canonical, text_hash
from llm_controller.memory_http import MemoryHTTPClient, MemoryServiceError
from llm_controller.memory_prompt import RetrievalPrompt, original_query, QUERY_SCHEMA
from llm_controller.qwen_step import MODEL
from validation.memory_service_session import memory_service, offline_env


def require(condition, message):
    if not condition:
        raise ValueError(message)


def make_cases(step_dir, client, fixtures):
    cases = []
    for i, row in enumerate(fixtures):
        path = personal_path(step_dir/('step-{:04d}.json'.format(row['step_id'])))
        raw = path.read_bytes()
        step = json.loads(raw)
        require(step['model'] == MODEL and step['memory_mode'] == 'off', 'Expected saved Qwen off step')
        calls = [call for call in step['calls'] if call['stage'] == 'action' and
                 call['context']['vehicle_id'] == row['vehicle_id']]
        require(len(calls) == 1, 'Expected unique saved action')
        messages = calls[0]['messages']
        require(len(messages) == 1 and messages[0]['role'] == 'system', 'Expected single system prompt')
        base = messages[0]['content']
        require(base.count('\nCurrent scenario:\n') == 1 and base.count('\nRules:\n') == 1,
                'Scenario boundary mismatch')
        scenario = base.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
        query = original_query(scenario)
        require(query == row['query'], 'Original query differs from R2 fixture')
        hits = client.retrieve(query, top_k=2)
        require(len(hits) == 2 and hits[0]['id'] == 'fixture-'+str(i), 'Real retrieval top-1 mismatch')
        cases.append(dict(scenario=scenario, base_prompt=base, hits=hits,
                          source_step=str(path), source_step_sha256=text_hash(raw.decode('utf-8')),
                          vehicle_id=row['vehicle_id']))
    return cases


def prepare_cases(cases, view):
    records = []
    for case in cases:
        prompt, receipt = view.prepare(case['scenario'], case['base_prompt'])
        require(receipt['candidates'] == case['hits'], 'Retrieved candidates changed since token counting')
        records.append(dict(source_step=case['source_step'], source_step_sha256=case['source_step_sha256'],
                            vehicle_id=case['vehicle_id'], messages=[dict(role='system', content=prompt)],
                            **receipt))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--step-dir', type=Path)
    parser.add_argument('--port', type=int, default=18082)
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == 'aarch64' and
            sys.version_info[:2] == (3, 8) and
            Path(sys.prefix) == Path('/home/nclab/Yizhen/envs/codriving-sim-py38'),
            'Existing Spark simulation Python 3.8 required')
    personal_path(ROOT)
    run = personal_path(args.run_dir)
    require(run.is_dir(), 'Fresh run directory required')
    if args.step_dir is None:
        choices = sorted({p.parent for p in personal_path(
            Path('/home/nclab/Yizhen/runs/M16-one-episode')).rglob('step-0000.json')})
        require(len(choices) == 1, 'Supply --step-dir for unique existing M16 source')
        args.step_dir = choices[0]
    step_dir = personal_path(args.step_dir)
    fixture_bytes = (ROOT/'modification_reports/M20-local-memory/R2-memory-semantics/fixtures.json').read_bytes()
    fixtures = json.loads(fixture_bytes)['rows']
    expected = manifest(QUERY_SCHEMA)
    client = MemoryHTTPClient(expected, args.port)
    metadata = [dict(row['would_write']['metadata'], source=dict(test_only=True, fixture_index=i,
                     fixture_sha256=text_hash(fixture_bytes.decode('utf-8')))) for i, row in enumerate(fixtures)]
    with memory_service(run/'create', run/'test-chroma', expected, args.port, create=True):
        for i, row in enumerate(fixtures):
            client.add('fixture-'+str(i), row['would_write']['page_content'], metadata[i])
        before = client.status()['snapshot_sha256']
        try:
            client.add('oversize-test', 'word '*300, metadata[0])
        except MemoryServiceError:
            pass
        else:
            raise ValueError('Over-256-token MiniLM input unexpectedly accepted')
        require(client.status()['snapshot_sha256'] == before, 'Rejected write changed corpus')
    with memory_service(run/'readonly', run/'test-chroma', expected, args.port):
        require(client.status()['snapshot_sha256'] == before, 'Reopen corpus differs')
        cases = make_cases(step_dir, client, fixtures)
        for case in cases:
            for hit in case['hits']:
                index = int(hit['id'].split('-')[1])
                require(hit['metadata'] == metadata[index] and
                        hit['text'] == fixtures[index]['would_write']['page_content'], 'Source/text/metadata mismatch')
        case_file = run/'retrieved-cases.json'
        case_file.write_text(canonical(cases)+'\n', encoding='utf-8')
        tokenizer_dir = personal_path(run/'tokenizer')
        tokenizer_dir.mkdir()
        counts_path = tokenizer_dir/'counts.json'
        with (tokenizer_dir/'console.txt').open('x', encoding='utf-8') as output:
            subprocess.run(['/home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python',
                            str(ROOT/'validation/count_memory_candidates.py'), '--cases', str(case_file),
                            '--output', str(counts_path)], env=offline_env(tokenizer_dir),
                           stdout=output, stderr=subprocess.STDOUT, timeout=120, check=True)
        counts = json.loads(counts_path.read_text(encoding='utf-8'))
        require(counts['status'] == 'PASS' and
                counts['cases_sha256'] == text_hash(case_file.read_text(encoding='utf-8')), 'Tokenizer receipt mismatch')
        def count(messages):
            return counts['counts'][text_hash(canonical(messages))]
        records = prepare_cases(cases, RetrievalPrompt(client, count))
        require(client.status()['snapshot_sha256'] == before, 'Retrieval-only corpus changed')
        require(not any(name in sys.modules for name in ('torch', 'chromadb', 'transformers')),
                'Simulation client imported ML dependency')
    result = dict(status='PASS', client_python=sys.version, manifest=expected,
                  snapshot_sha256=before, records=records, oversize_minilm_rejected_without_write=True,
                  limitation='Two test-only real retrievals and tokenizer budget; no Qwen generation, traffic step or production on.')
    (run/'acceptance.json').write_text(canonical(result)+'\n', encoding='utf-8')
    print('M21-R2 real retrieval -> prompt: PASS; cases={}; max_input_tokens={}'.format(
        len(records), max(row['input_tokens'] for row in records)))


if __name__ == '__main__':
    main()
