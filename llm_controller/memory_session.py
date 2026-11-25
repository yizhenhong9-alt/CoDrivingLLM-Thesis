"""M21-R4 scoped readonly retrieval and token counting; stdlib only."""
import json
from pathlib import Path
from .local_memory import manifest, personal_path, text_hash
from .memory_http import MemoryHTTPClient, QWEN_TOKENIZER
from .memory_prompt import RetrievalPrompt, QUERY_SCHEMA


class OnlineMemorySession:
    """One caller-owned scope, externally owned service; no service stop/write."""
    mode = 'retrieve-only'

    def __init__(self, config, *, _client=None):
        keys = {'format', 'manifest', 'port', 'timeout', 'snapshot_sha256', 'context_limit', 'output_tokens'}
        if (not isinstance(config, dict) or set(config) != keys or
                config['format'] != 'm21-r4-readonly-v1' or config['manifest'] != manifest(QUERY_SCHEMA) or
                config['context_limit'] != 2048 or config['output_tokens'] != 256 or
                not isinstance(config['snapshot_sha256'], str) or len(config['snapshot_sha256']) != 64 or
                any(c not in '0123456789abcdef' for c in config['snapshot_sha256'])):
            raise ValueError('Explicit readonly memory session config required')
        self.config = config
        self.client = _client or MemoryHTTPClient(config['manifest'], config['port'], config['timeout'])
        self.active = False
        self.receipt = dict(mode=self.mode, opened=False, closed=False, queries=0, token_checks=0,
                            expected_snapshot_sha256=config['snapshot_sha256'])
        self.view = RetrievalPrompt(self.client, self.count_messages,
                                    output_tokens=config['output_tokens'], context_limit=config['context_limit'])

    @classmethod
    def from_file(cls, path):
        path = personal_path(Path(path))
        config = json.loads(path.read_text(encoding='utf-8'))
        session = cls(config)
        session.receipt['config_sha256'] = text_hash(path.read_text(encoding='utf-8'))
        return session

    def _check_status(self):
        status = self.client.status()
        if (status.get('writable') is not False or status.get('tokenizer') != QWEN_TOKENIZER or
                status.get('snapshot_sha256') != self.config['snapshot_sha256']):
            raise ValueError('Readonly memory session identity/corpus mismatch')
        return status

    def __enter__(self):
        if self.active or self.receipt['closed']:
            raise ValueError('Memory session cannot be reopened')
        try:
            self._check_status()
        except BaseException:
            self.close()
            raise
        self.active = True
        self.receipt['opened'] = True
        return self

    def count_messages(self, messages):
        if not self.active:
            raise ValueError('Memory session is not active')
        count = self.client.count_messages(messages)
        self.receipt['token_checks'] += 1
        return count

    def check_request(self, messages, stage):
        count = self.count_messages(messages)
        if count+self.config['output_tokens'] > self.config['context_limit']:
            raise ValueError('Complete request plus output exceeds context')
        return dict(stage=stage, input_tokens=count, output_tokens=self.config['output_tokens'],
                    context_limit=self.config['context_limit'])

    def prepare(self, scenario, base_prompt):
        if not self.active:
            raise ValueError('Memory session is not active')
        self._check_status()
        result = self.view.prepare(scenario, base_prompt)
        self._check_status()
        self.receipt['queries'] += 1
        return result

    def close(self):
        if not self.receipt['closed']:
            self.active = False
            self.client.opener.close()
            self.receipt['closed'] = True

    def __exit__(self, exc_type, exc, tb):
        try:
            self._check_status()
            self.receipt['final_snapshot_verified'] = True
        except Exception as error:
            self.receipt['final_snapshot_error'] = type(error).__name__
            if exc_type is None:
                raise
        finally:
            self.close()
