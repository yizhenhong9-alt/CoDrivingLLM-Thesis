"""M21-R1 original memory wording plus explicit complete-message token budget.

No writes, query normalization, safety rules or model/network imports here.
"""
from .local_memory import canonical, text_hash

INTRO = ('Here is your action when scenarios are similar to the current scenario in the past, '
         'you should learn from past memory try not to take the cation that cause more danger:\n')
ENDING = ('Above messages are some examples of how you make a decision in the past. '
          'Those scenarios are similar to the current scenario. You should refer to those '
          'examples to make a decision for the current scenario.')
MARKER = '\nConflicts and suggested passing orders (when suggested to pass second, better to slow down):\n'
QUERY_SCHEMA = 'original-prompt-info-last-two-lines-v1'


def original_query(prompt_info):
    if not isinstance(prompt_info, str) or not prompt_info.strip():
        raise ValueError('Nonempty original prompt_info required')
    return '\n'.join(prompt_info.strip().split('\n')[-2:])


def original_experience(hits):
    experience = ''
    for hit in hits:
        metadata = hit['metadata']
        if any(not isinstance(metadata.get(key), str) for key in
               ('human_question', 'negotiation_result', 'final_action', 'comments')):
            raise ValueError('Original four string metadata fields required')
        experience += '- Last time {}, you choose to {}, it is {}\n'.format(
            metadata['negotiation_result'], metadata['final_action'], metadata['comments'])
    # Preserve original empty-library wording; record actual 0 hits separately.
    return experience+ENDING


def fit_prompt(base_prompt, hits, count_messages, *, output_tokens, context_limit):
    if (type(output_tokens) is not int or output_tokens <= 0 or
            type(context_limit) is not int or context_limit <= 0):
        raise ValueError('Explicit positive integer token limits required')
    if not isinstance(hits, list) or len(hits) > 2:
        raise ValueError('Expected original top_k=2 candidates')
    if base_prompt.count(MARKER) != 1:
        raise ValueError('Expected one original Qwen passing-orders boundary')
    # Validate all candidates even when a later candidate would be excluded.
    original_experience(hits)
    attempts = []
    for size in range(len(hits), -1, -1):
        section = '\n'+INTRO+original_experience(hits[:size])+'\n'
        prompt = base_prompt.replace(MARKER, section+MARKER, 1)
        messages = [{'role': 'system', 'content': prompt}]
        count = count_messages(messages)
        if type(count) is not int or count < 1:
            raise ValueError('Counter must return complete chat-template token count')
        attempts.append(dict(memory_count=size, input_tokens=count,
                             required_tokens=count+output_tokens))
        if count+output_tokens <= context_limit:
            return prompt, dict(candidate_count=len(hits), injected_count=size,
                                excluded_count=len(hits)-size,
                                exclusion_reason='token_budget' if size < len(hits) else None,
                                input_tokens=count, output_tokens=output_tokens,
                                context_limit=context_limit, attempts=attempts,
                                base_prompt_sha256=text_hash(base_prompt),
                                final_prompt_sha256=text_hash(prompt))
    raise ValueError('Complete prompt plus output exceeds context even with zero memories')


class RetrievalPrompt:
    """Caller-owned readonly client; fixture integration until live gate is tested."""
    def __init__(self, client, count_messages, *, output_tokens=256, context_limit=2048):
        if client.manifest['query_schema'] != QUERY_SCHEMA:
            raise ValueError('Explicit original query schema required; do not reuse R7 test DB')
        self.client, self.count_messages = client, count_messages
        self.output_tokens, self.context_limit = output_tokens, context_limit

    def prepare(self, scenario, base_prompt):
        query = original_query(scenario)
        before = self.client.status()
        if before.get('writable') is not False:
            raise ValueError('M21 retrieval-only requires adapter readonly service')
        hits = self.client.retrieve(query, top_k=2)
        after = self.client.status()
        if after.get('writable') is not False or before['snapshot_sha256'] != after['snapshot_sha256']:
            raise ValueError('Corpus changed during retrieval-only preparation')
        prompt, receipt = fit_prompt(base_prompt, hits, self.count_messages,
                                     output_tokens=self.output_tokens, context_limit=self.context_limit)
        receipt.update(query=query, query_sha256=text_hash(query), manifest=self.client.manifest,
                       snapshot_sha256=after['snapshot_sha256'], candidates=hits,
                       injected_ids=[hit['id'] for hit in hits[:receipt['injected_count']]],
                       candidate_sha256=text_hash(canonical(hits)))
        return prompt, receipt
