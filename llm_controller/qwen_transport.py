"""Loopback-only HTTP transport and explicitly synthetic offline replies."""
import json
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .qwen_step import MODEL


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RuntimeError("Model endpoint redirects are forbidden")


class LocalQwen:
    mode = "live"

    def __init__(self, port=18080, timeout=120, max_tokens=256):
        if type(port) is not int or not 1 <= port <= 65535 or timeout <= 0 or max_tokens < 1:
            raise ValueError("Invalid request settings")
        self.base = "http://127.0.0.1:{}/v1".format(port)
        self.timeout, self.max_tokens = timeout, max_tokens
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.last_response = None

    def _request(self, path, body=None):
        request = Request(self.base + path,
                          data=None if body is None else json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def preflight(self):
        response = self._request("/models")
        if MODEL not in [item.get("id") for item in response.get("data", [])]:
            raise RuntimeError("Required model name is absent from /v1/models")
        return response

    def complete(self, messages, stage, context):
        self.last_response = None
        self.last_response = self._request("/chat/completions", {
            "model": MODEL, "messages": messages, "temperature": 0,
            "max_tokens": self.max_tokens, "stream": False})
        choice = self.last_response["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise RuntimeError("Incomplete generation: " + str(choice.get("finish_reason")))
        message = choice["message"]
        if message.get("refusal") or not isinstance(message.get("content"), str):
            raise RuntimeError("Missing text or refusal from model")
        return message["content"]


class FixtureReplies:
    """Arbitrary low-ID-first / IDLE fixtures; never a safety policy."""
    mode = "fixture"

    def __init__(self, parser_mode):
        self.parser_mode = parser_mode

    def complete(self, messages, stage, context):
        if stage == "negotiation":
            decisions = []
            for pair in context["pairs"]:
                first, second = sorted(pair)
                if self.parser_mode == "legacy":
                    first, second = context["names"][first], context["names"][second]
                decisions.append(dict(first_vehicle=first, second_vehicle=second))
            return json.dumps({"decisions": decisions})
        if self.parser_mode == "legacy":
            return 'Final Answer: "decision": {"IDLE"}'
        return json.dumps({"vehicle_id": context["vehicle_id"], "decision": "IDLE"})
