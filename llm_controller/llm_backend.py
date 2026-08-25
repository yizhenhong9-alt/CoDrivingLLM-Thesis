import json
import time
from urllib import request


class ChatBackend:
    """Minimal chat transport that leaves prompts and downstream parsers unchanged."""

    def __init__(self, backend="openai", model=None, endpoint=None, timeout=120,
                 openai_api_key=None, openai_proxy="http://127.0.0.1:7890"):
        self.backend = backend.lower()
        self.model = model or ("gpt-4o-mini" if self.backend == "openai" else None)
        self.endpoint = endpoint or (
            "https://api.openai.com/v1" if self.backend == "openai"
            else "http://127.0.0.1:11434"
        )
        self.timeout = timeout
        self.openai_api_key = openai_api_key
        self.openai_proxy = openai_proxy
        self.last_messages = None
        self.last_raw_response = None
        self.last_content = None
        self.last_latency_seconds = None

        if self.backend not in {"openai", "ollama"}:
            raise ValueError("Unsupported LLM backend: {}".format(backend))
        if not self.model:
            raise ValueError("An explicit model is required for the Ollama backend")

    def complete(self, messages):
        self.last_messages = messages
        started = time.perf_counter()
        try:
            if self.backend == "openai":
                content, raw_response = self._complete_openai(messages)
            else:
                content, raw_response = self._complete_ollama(messages)
        finally:
            self.last_latency_seconds = time.perf_counter() - started

        self.last_raw_response = raw_response
        self.last_content = content
        return content

    def _complete_openai(self, messages):
        import httpx
        from openai import OpenAI

        http_client = httpx.Client(proxies={
            "http://": self.openai_proxy,
            "https://": self.openai_proxy,
        })
        client = OpenAI(
            api_key=self.openai_api_key,
            base_url=self.endpoint,
            http_client=http_client,
        )
        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return completion.choices[0].message.content, completion.model_dump()

    def _complete_ollama(self, messages):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.endpoint.rstrip("/") + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            raw_response = json.loads(response.read().decode("utf-8"))

        message = raw_response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Ollama response is missing message.content")
        return message["content"], raw_response
