import json
import time
from urllib import request


class OllamaEmbeddingsAdapter:
    """Minimal Ollama adapter for LangChain's synchronous embedding interface."""

    def __init__(self, endpoint, model, timeout=120):
        if not endpoint:
            raise ValueError("An explicit Ollama embedding endpoint is required")
        if not model:
            raise ValueError("An explicit Ollama embedding model is required")

        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.vector_dimension = None
        self.request_count = 0
        self.last_request = None
        self.last_raw_response = None
        self.last_latency_seconds = None

    def embed_documents(self, texts):
        if not isinstance(texts, list) or not texts:
            raise ValueError("embed_documents requires a non-empty list of strings")
        if not all(isinstance(text, str) for text in texts):
            raise TypeError("Every embedding input must be a string")
        return self._embed(texts)

    def embed_query(self, text):
        if not isinstance(text, str):
            raise TypeError("Embedding query must be a string")
        return self._embed([text])[0]

    def _embed(self, texts):
        payload = {"model": self.model, "input": texts}
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.endpoint + "/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.perf_counter()
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        finally:
            self.last_latency_seconds = time.perf_counter() - started

        embeddings = raw_response.get("embeddings") if isinstance(raw_response, dict) else None
        self._validate_embeddings(embeddings, len(texts))

        response_model = raw_response.get("model")
        if response_model is not None and not isinstance(response_model, str):
            raise ValueError("Ollama embedding response has an invalid model field")

        self.request_count += 1
        self.last_request = payload
        self.last_raw_response = raw_response
        return embeddings

    def _validate_embeddings(self, embeddings, expected_count):
        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            raise ValueError("Ollama embedding response count does not match input count")

        dimensions = set()
        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise ValueError("Ollama embedding response contains an empty vector")
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                       for value in vector):
                raise ValueError("Ollama embedding vector contains a non-numeric value")
            dimensions.add(len(vector))

        if len(dimensions) != 1:
            raise ValueError("Ollama embedding response contains inconsistent dimensions")

        dimension = dimensions.pop()
        if self.vector_dimension is None:
            self.vector_dimension = dimension
        elif dimension != self.vector_dimension:
            raise ValueError("Ollama embedding dimension changed during the run")

