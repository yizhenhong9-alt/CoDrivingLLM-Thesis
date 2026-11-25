"""M22 original retrieve -> answer -> pre-step update semantics; stdlib client."""
from contextlib import redirect_stdout
import io
from .local_memory import canonical, manifest, text_hash
from .memory_http import MemoryHTTPClient, QWEN_TOKENIZER
from .memory_session import OnlineMemorySession
from .memory_prompt import QUERY_SCHEMA, original_query, fit_prompt


def original_payload(action_agent, scenario, action_id):
    """Call the preserved original method, suppressing its premature success print."""
    rows = []
    class Capture:
        def addMemory(self, text, human_question, negotiation, action, comments):
            rows.append(dict(text=text, metadata=dict(human_question=human_question,
                negotiation_result=negotiation, final_action=action, comments=comments)))
    with redirect_stdout(io.StringIO()):
        action_agent.memory_update(Capture(), scenario, [action_id])
    if (len(rows) != 1 or rows[0]['text'] != scenario.strip().split('\n')[-1] or
            rows[0]['metadata']['human_question'] != 'None' or
            rows[0]['metadata']['negotiation_result'] != 'None' or
            rows[0]['metadata']['final_action'] != str([action_id])):
        raise ValueError('Original memory payload differs from reviewed semantics')
    return rows[0]


class OriginalMemorySession(OnlineMemorySession):
    """Mutable shared corpus, one cooperating writer; only own writes advance snapshot."""
    mode = 'on'

    def __init__(self, config, *, _client=None):
        keys = {'format', 'manifest', 'port', 'timeout', 'store_path_sha256',
                'context_limit', 'output_tokens', 'test_only'}
        digest = config.get('store_path_sha256') if isinstance(config, dict) else None
        if (not isinstance(config, dict) or set(config) != keys or
                config['format'] != 'm22-original-v1' or config['manifest'] != manifest(QUERY_SCHEMA) or
                config['context_limit'] != 2048 or config['output_tokens'] != 256 or
                type(config['test_only']) is not bool or not isinstance(digest, str) or
                len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Explicit original memory-on config required')
        self.config = config
        self.client = _client or MemoryHTTPClient(config['manifest'], config['port'], config['timeout'])
        self.active = False
        self._snapshot, self._count = None, None
        self.receipt = dict(mode='on', method='original-per-vehicle-pre-step', opened=False,
                            closed=False, queries=0, writes=0, token_checks=0, test_only=config['test_only'])

    def _identity(self, status):
        if (status.get('writable') is not True or status.get('tokenizer') != QWEN_TOKENIZER or
                status.get('store_path_sha256') != self.config['store_path_sha256'] or
                type(status.get('count')) is not int or status['count'] < 0 or
                not isinstance(status.get('snapshot_sha256'), str) or len(status['snapshot_sha256']) != 64):
            raise ValueError('Writable original memory service identity mismatch')

    def _check_status(self):
        status = self.client.status()
        self._identity(status)
        if self._snapshot is None:
            self._snapshot, self._count = status['snapshot_sha256'], status['count']
            self.receipt.update(initial_snapshot_sha256=self._snapshot, initial_count=self._count)
        elif status['snapshot_sha256'] != self._snapshot or status['count'] != self._count:
            raise ValueError('Memory corpus changed outside this session')
        self.receipt.update(final_snapshot_sha256=self._snapshot, final_count=self._count)
        return status

    def prepare(self, scenario, base_prompt):
        if not self.active:
            raise ValueError('Memory session is not active')
        before = self._check_status()
        query = original_query(scenario)
        hits = self.client.retrieve(query, top_k=2)
        self._check_status()
        prompt, receipt = fit_prompt(base_prompt, hits, self.count_messages,
                                    output_tokens=256, context_limit=2048)
        receipt.update(query=query, query_sha256=text_hash(query), manifest=self.config['manifest'],
                       snapshot_sha256=before['snapshot_sha256'], corpus_count=before['count'],
                       candidates=hits, injected_ids=[h['id'] for h in hits[:receipt['injected_count']]],
                       candidate_sha256=text_hash(canonical(hits)))
        self.receipt['queries'] += 1
        return prompt, receipt

    def make_update(self, action_agent, scenario, action_id, *, episode_id, step_id, vehicle_id, code_commit):
        if not self.active:
            raise ValueError('Memory session is not active')
        row = original_payload(action_agent, scenario, action_id)
        row['metadata']['source'] = dict(method='original-per-vehicle-pre-step',
            comments_kind='original-generate-comment-heuristic-not-outcome', episode_id=episode_id,
            step_id=step_id, vehicle_id=vehicle_id, code_commit=code_commit,
            test_only=self.config['test_only'])
        row.update(id='m22/{}/{}/{}'.format(episode_id, step_id, vehicle_id),
                   status='prepared', snapshot_before=self._snapshot, count_before=self._count)
        return row

    def commit_update(self, event):
        self._check_status()
        if event['status'] != 'prepared' or event['snapshot_before'] != self._snapshot:
            raise ValueError('Stale/duplicate memory update')
        event['status'] = 'attempted'
        try:
            receipt = self.client.add(event['id'], event['text'], event['metadata'])
            after = self.client.status()
            self._identity(after)
            if after['count'] != self._count+1 or after['snapshot_sha256'] == self._snapshot:
                raise ValueError('Write receipt/corpus verification failed; do not retry')
            self._snapshot, self._count = after['snapshot_sha256'], after['count']
            self.receipt['writes'] += 1
            self.receipt.update(final_snapshot_sha256=self._snapshot, final_count=self._count)
            event.update(status='verified', write_receipt=receipt, snapshot_after=self._snapshot,
                         count_after=self._count)
        except Exception as error:
            event.update(status='failed-outcome-unknown-do-not-retry', error_type=type(error).__name__)
            raise
