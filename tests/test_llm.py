"""Exercise the real GeminiClient against a local fake HTTP server (no network, no API key, no cost).

This checks the exact request we send (JSON mode, a schema, system prompt, base64 image parts, no
sampling parameters), how the reply and token usage are read, and how HTTP failures map to retries.
"""
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from invoice_extractor.config import Settings
from invoice_extractor.llm import GeminiClient, LLMError, call_with_retries, make_client, to_gemini_schema
from invoice_extractor.schema import EXTRACTION_TOOL_SCHEMA
from fakes import invoice_payload


class FakeGemini:
    def __init__(self):
        self.requests = []
        self.script = []  # list of (status, body, delay_s)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                status, payload, delay = outer.script.pop(0) if outer.script else (200, outer.ok_body({}), 0)
                time.sleep(delay)
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def ok_body(data, prompt=321, out=45, thoughts=None, finish="STOP", text=None):
        meta = {"promptTokenCount": prompt, "candidatesTokenCount": out, "totalTokenCount": prompt + out + (thoughts or 0)}
        if thoughts is not None:
            meta["thoughtsTokenCount"] = thoughts
        return {
            "candidates": [{"content": {"role": "model", "parts": [{"text": text if text is not None else json.dumps(data)}]}, "finishReason": finish, "index": 0}],
            "usageMetadata": meta,
            "modelVersion": "fake",
        }

    @staticmethod
    def error_body(code, status, message="x"):
        return {"error": {"code": code, "message": message, "status": status}}

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def api():
    fake = FakeGemini()
    yield fake
    fake.close()


S = Settings(timeout_s=5.0)


def client_for(api, settings=S):
    return GeminiClient(settings, api_key="test-key", base_url=api.url)


def call(client, content=None, model="gemini-3.5-flash-lite"):
    return client.extract(model=model, system="sys prompt", content=content or [{"type": "text", "text": "hello"}],
                          tool_schema=EXTRACTION_TOOL_SCHEMA, max_tokens=777)


def test_schema_conversion_marks_nullable_and_keeps_order():
    g = to_gemini_schema(EXTRACTION_TOOL_SCHEMA)
    assert g["properties"]["vendor"] == {"nullable": True, "type": "string", "description": "Name of the seller that issued the invoice."}
    assert g["property_ordering"][0] == "document_type"
    assert "additionalProperties" not in json.dumps(g)
    assert g["properties"]["line_items"]["items"]["required"] == ["description", "quantity", "amount"]


def test_request_shape_and_response_parsing(api):
    api.script = [(200, api.ok_body(invoice_payload(), prompt=1093, out=45, thoughts=119), 0)]
    content = [{"type": "text", "text": "hi"}, {"type": "image", "media_type": "image/jpeg", "data": base64.b64encode(b"JPEGDATA").decode()}]
    result = call(client_for(api), content, model="gemini-3.5-flash")
    assert result.data["vendor"] == "Sharma Office Supplies Pvt Ltd"
    assert result.usage.input_tokens == 1093
    assert result.usage.output_tokens == 45 + 119  # hidden thinking tokens are billed as output

    req = api.requests[0]
    assert req["path"].endswith("/models/gemini-3.5-flash:generateContent")
    assert req["headers"]["x-goog-api-key"] == "test-key"
    body = req["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "sys prompt"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "hi"}
    inline = parts[1]["inlineData"]
    assert base64.b64decode(inline["data"]) == b"JPEGDATA"
    assert (inline.get("mimeType") or inline.get("mime_type")) == "image/jpeg"  # the SDK may use either spelling
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and cfg["maxOutputTokens"] == 777
    assert cfg["responseSchema"]["properties"]["vendor"]["nullable"] is True
    ordering = cfg["responseSchema"].get("propertyOrdering") or cfg["responseSchema"].get("property_ordering")
    assert ordering[0] == "document_type"  # the model fills the document type first
    for banned in ("temperature", "topP", "topK"):
        assert banned not in cfg


def test_json_wrapped_in_a_code_fence_is_still_parsed(api):
    api.script = [(200, api.ok_body(None, text="```json\n" + json.dumps({"vendor": "Acme"}) + "\n```"), 0)]
    assert call(client_for(api)).data == {"vendor": "Acme"}


@pytest.mark.parametrize(
    "status,gstatus,kind,retryable",
    [(429, "RESOURCE_EXHAUSTED", "rate_limit", True), (503, "UNAVAILABLE", "server_error", True), (500, "INTERNAL", "server_error", True),
     (401, "UNAUTHENTICATED", "auth", False), (403, "PERMISSION_DENIED", "auth", False),
     (400, "INVALID_ARGUMENT", "bad_request", False), (404, "NOT_FOUND", "bad_request", False)],
)
def test_http_errors_map_to_llm_errors(api, status, gstatus, kind, retryable):
    api.script = [(status, api.error_body(status, gstatus), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == kind and err.value.retryable is retryable


DAILY_MESSAGE = (
    "You exceeded your current quota. * Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash. "
    "Generate content requests per day limit exceeded on Free Tier"
)


def test_a_daily_quota_429_is_not_retryable(api):
    api.script = [(429, api.error_body(429, "RESOURCE_EXHAUSTED", DAILY_MESSAGE), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "quota" and err.value.retryable is False
    assert "midnight Pacific" in str(err.value)


def test_a_zero_limit_429_means_the_tier_has_no_access_and_is_not_retryable(api):
    api.script = [(429, api.error_body(429, "RESOURCE_EXHAUSTED", "quota exceeded, limit: 0, model: gemini-x"), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "quota" and not err.value.retryable


def test_a_per_minute_429_stays_retryable(api):
    msg = "Quota exceeded for metric generate_content_free_tier_requests, limit: 15, per minute"
    api.script = [(429, api.error_body(429, "RESOURCE_EXHAUSTED", msg), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "rate_limit" and err.value.retryable


def test_rate_limit_reads_the_suggested_wait(api):
    body = {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED",
                      "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"}]}}
    api.script = [(429, body, 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "rate_limit" and err.value.retry_after == 34.0


def test_timeout_is_retryable(api):
    api.script = [(200, api.ok_body({}), 2.0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api, Settings(timeout_s=0.3)))
    assert err.value.kind == "timeout" and err.value.retryable


def test_connection_refused_is_retryable(api):
    dead = GeminiClient(S, api_key="k", base_url="http://127.0.0.1:9")
    with pytest.raises(LLMError) as err:
        call(dead)
    assert err.value.kind in ("connection", "timeout") and err.value.retryable


def test_truncated_blocked_and_empty_replies(api):
    api.script = [(200, api.ok_body({"vendor": "x"}, finish="MAX_TOKENS"), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "truncated"

    api.script = [(200, api.ok_body({}, finish="SAFETY"), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "refusal" and not err.value.retryable

    api.script = [(200, api.ok_body(None, text="not json at all"), 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "bad_output"

    api.script = [(200, {"candidates": [], "usageMetadata": {"promptTokenCount": 5}}, 0)]
    with pytest.raises(LLMError) as err:
        call(client_for(api))
    assert err.value.kind == "bad_output"


def test_missing_key_message():
    with pytest.raises(LLMError) as err:
        GeminiClient(S)  # conftest removes GEMINI_API_KEY from the environment
    assert "GEMINI_API_KEY" in str(err.value)


def test_unknown_provider_is_a_clear_error():
    with pytest.raises(ValueError):
        make_client(Settings(provider="nope"))


def test_retry_wrapper_backs_off_and_gives_up():
    sleeps, attempts = [], []

    def flaky():
        attempts.append(1)
        raise LLMError("rate_limit", "429", retryable=True)

    with pytest.raises(LLMError):
        call_with_retries(flaky, attempts=3, backoff_s=1.0, sleep=sleeps.append)
    assert len(attempts) == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0]

    attempts.clear()
    with pytest.raises(LLMError):
        call_with_retries(lambda: (_ for _ in ()).throw(LLMError("auth", "no", retryable=False)), attempts=3, backoff_s=1.0, sleep=sleeps.append)


def test_retry_wrapper_honours_the_suggested_wait():
    sleeps = []
    calls = []

    def once_then_ok():
        calls.append(1)
        if len(calls) == 1:
            raise LLMError("rate_limit", "429", retryable=True, retry_after=20.0)
        return "ok"

    result, retries = call_with_retries(once_then_ok, attempts=3, backoff_s=0.1, sleep=sleeps.append)
    assert result == "ok" and retries == 1 and sleeps == [20.0]


def test_each_retry_is_announced_so_a_wait_never_looks_like_a_freeze(caplog):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise LLMError("server_error", "503", retryable=True)
        return "ok"

    with caplog.at_level("WARNING", logger="invoice_extractor.llm"):
        result, retries = call_with_retries(flaky, attempts=5, backoff_s=0.0, sleep=lambda s: None, label="gemini-x")
    assert result == "ok" and retries == 2
    assert [r.getMessage() for r in caplog.records] == [
        "gemini-x: server_error, retry 1 of 4 in 0s",
        "gemini-x: server_error, retry 2 of 4 in 0s",
    ]


def test_a_quota_error_is_raised_at_once_without_sleeping():
    sleeps = []
    with pytest.raises(LLMError) as err:
        call_with_retries(lambda: (_ for _ in ()).throw(LLMError("quota", "daily")), attempts=5, backoff_s=3.0, sleep=sleeps.append)
    assert err.value.kind == "quota" and sleeps == []
