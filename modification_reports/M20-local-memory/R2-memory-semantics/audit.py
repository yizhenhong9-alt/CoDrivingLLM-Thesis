"""Replay original memory text methods against saved M16 prompts, without a DB/API.

This reconstructs inputs on the off trajectory, never a memory-on counterfactual.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def methods(path, names):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(found) != len(names):
        raise ValueError('Expected exact original method set')
    namespace = {'re': re, 'print': lambda *args, **kwargs: None}
    exec(compile(ast.Module(body=found, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class CaptureMemory:
    def __init__(self):
        self.writes = []
        self.queries = []
        self.results = []

    def addMemory(self, *args):
        self.writes.append(dict(page_content=args[0], metadata=dict(
            human_question=args[1], negotiation_result=args[2], final_action=args[3], comments=args[4])))

    def retrieveMemory(self, query, top_k):
        self.queries.append(dict(query=query, top_k=top_k))
        return self.results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, default=ROOT.parent/'CoDrivingLLM')
    parser.add_argument('--steps', type=Path, default=ROOT.parent/'runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('audit.json'))
    args = parser.parse_args()
    action_file = args.original/'llm_controller/llm_agent_action.py'
    prompt_file = args.original/'llm_controller/prompt_llm.py'
    functions = methods(action_file, {'relative_memory', 'memory_update'})
    functions['memory_update'].__globals__['generate_comment'] = methods(prompt_file, {'generate_comment'})['generate_comment']
    counts, rows, hashes = Counter(), [], {}
    for path in sorted(args.steps.glob('step-*.json')):
        hashes[path.name] = sha(path)
        step = json.loads(path.read_text(encoding='utf-8'))
        for call in step['calls']:
            if call['stage'] != 'action':
                continue
            counts['action_prompts'] += 1
            content = call['messages'][0]['content']
            if content.count('\nCurrent scenario:\n') != 1 or content.count('\nRules:\n') != 1:
                raise ValueError('Ambiguous scenario boundaries')
            scenario = content.split('\nCurrent scenario:\n', 1)[1].split('\nRules:\n', 1)[0]
            counts['scenario_extracted'] += 1
            chosen = call['parsers']['strict']['value']
            capture = CaptureMemory()
            row = dict(step_id=step['step_id'], vehicle_id=call['context']['vehicle_id'],
                       action_id=chosen['action_id'], decision=chosen['decision'])
            functions['relative_memory'](None, capture, scenario)
            row.update(capture.queries[0])
            try:
                # Single-element Python list has the same str as the original
                # one-element integer ndarray: '[1]', '[3]' or '[4]'.
                functions['memory_update'](None, capture, scenario, [chosen['action_id']])
                if len(capture.writes) != 1:
                    raise ValueError('Unexpected write count')
                row['would_write'] = capture.writes[0]
                counts['update_completed_to_capture'] += 1
                page = row['would_write']['page_content']
                counts['empty_info' if page.strip() == 'Conflict info is empty' else 'danger_detail'] += 1
                counts['query_exactly_equals_page'] += row['query'] == page
                counts['query_strip_equals_page_strip'] += row['query'].strip() == page.strip()
                counts['query_equals_newline_plus_page'] += row['query'] == '\n'+page
                # Format-only demonstration if this metadata were a search hit.
                # This does NOT assert it would actually be selected by an index.
                capture.results = [row['would_write']['metadata']]
                row['format_only_if_selected_as_hit'] = functions['relative_memory'](None, capture, scenario)
            except Exception as exc:
                row['update_error'] = type(exc).__name__+': '+str(exc)
                counts['update_failed'] += 1
            rows.append(row)
    if not rows:
        raise ValueError('No saved action prompts found')
    report = dict(scope='M16 101-step memory-off trajectory; original methods extracted via AST; no DB/API/models',
                  source_sha256={str(action_file): sha(action_file), str(prompt_file): sha(prompt_file)},
                  input_sha256=hashes, counts=dict(counts), rows=rows,
                  limitation='would_write and format-only examples are replay, not actual memory records or retrieved hits')
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(files=len(hashes), counts=dict(counts)), ensure_ascii=False, indent=2))
    for row in rows:
        if (row['step_id'], row['vehicle_id']) in ((35, 3), (35, 4), (42, 3)):
            print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
