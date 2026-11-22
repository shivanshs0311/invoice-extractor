"""LLM access. One small interface, one real implementation (Gemini), easy to fake in tests.

Design notes
* Output is forced into JSON that matches a schema (response_mime_type + response_schema), so the
  reply is data we validate, not free text we would have to parse.
* No sampling parameters are sent. Thinking models spend hidden "thought" tokens, which Google bills
  as output tokens, so we count them as output tokens.
* The SDK's own retries are turned off. We retry transient errors ourselves so every retry is
  counted and visible in the run log.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol, TypeVar
from collections.abc import Callable

from .config import Settings

T = TypeVar("T")
log = logging.getLogger("invoice_extractor.llm")


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0  # includes hidden thinking tokens, because they are billed as output
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass
class LLMResult:
    data: dict
    usage: Usage
    model: str
    latency_s: float
    stop_reason: Optional[str] = None


class LLMError(Exception):
    """kind is one of: timeout, connection, rate_limit, quota, server_error, auth, bad_request,
    refusal, truncated, bad_output.

    rate_limit is a per-minute limit: waiting helps. quota is a daily (or zero) allowance: waiting does not.
    """

    def __init__(self, kind: str, message: str, retryable: bool = False, retry_after: Optional[float] = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after


class LLMClient(Protocol):
    def extract(
        self, *, model: str, system: str, content: list[dict], tool_schema: dict, max_tokens: int
    ) -> LLMResult: ...


# --------------------------------------------------------------------------- #
# JSON Schema -> Gemini response schema
# --------------------------------------------------------------------------- #
def to_gemini_schema(node: dict) -> dict:
    """Convert our JSON Schema into the OpenAPI-style subset Gemini accepts.

    ["string", "null"] becomes {"type": "string", "nullable": true}; additionalProperties is dropped;
    property order is kept so the model fills document_type first.
    """
    out: dict[str, Any] = {}
    node_type = node.get("type")
    if isinstance(node_type, list):
        non_null = [t for t in node_type if t != "null"]
        node_type = non_null[0] if non_null else "string"
        if "null" in node["type"]:
            out["nullable"] = True
    if node_type:
        out["type"] = node_type
    for key in ("description", "enum", "required"):
        if key in node:
            out[key] = node[key]
    if "properties" in node:
        out["properties"] = {name: to_gemini_schema(sub) for name, sub in node["properties"].items()}
        out["property_ordering"] = list(node["properties"])
    if "items" in node:
        out["items"] = to_gemini_schema(node["items"])
    return out


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #
_BLOCKED = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "RECITATION"}


class GeminiClient:
    def __init__(self, settings: Settings, api_key: Optional[str] = None, base_url: Optional[str] = None):
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as exc:  # pragma: no cover
            raise LLMError("auth", "The 'google-genai' package is not installed. Run: pip install google-genai") from exc
        key = (api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if not key:
            raise LLMError("auth", "GEMINI_API_KEY is not set. Put it in the .env file (see .env.example).")
        self._types = types
        self._errors = errors
        options = types.HttpOptions(
            timeout=int(settings.timeout_s * 1000),  # milliseconds
            retry_options=types.HttpRetryOptions(attempts=1),  # no hidden SDK retries
            **({"base_url": base_url} if base_url else {}),
        )
        self._client = genai.Client(api_key=key, http_options=options)

    def _part(self, part: dict):
        types = self._types
        if part["type"] == "text":
            return types.Part.from_text(text=part["text"])
        return types.Part.from_bytes(data=base64.b64decode(part["data"]), mime_type=part["media_type"])

    def extract(
        self, *, model: str, system: str, content: list[dict], tool_schema: dict, max_tokens: int
    ) -> LLMResult:
        types, errors = self._types, self._errors
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=types.Schema.model_validate(to_gemini_schema(tool_schema)),
            max_output_tokens=max_tokens,
        )
        started = time.perf_counter()
        try:
            resp = self._client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=[self._part(p) for p in content])],
                config=config,
            )
        except errors.ClientError as exc:
            raise _map_client_error(exc) from exc
        except errors.ServerError as exc:
            raise LLMError("server_error", f"Server error {getattr(exc, 'code', '?')}", retryable=True, retry_after=_retry_delay(exc)) from exc
        except errors.APIError as exc:
            raise LLMError("server_error", f"API error: {_short(exc)}", retryable=True) from exc
        except Exception as exc:  # network and timeout errors come from the HTTP library underneath
            name = type(exc).__name__
            if "Timeout" in name or "timed out" in str(exc).lower():
                raise LLMError("timeout", f"Request timed out: {_short(exc)}", retryable=True) from exc
            if any(w in name for w in ("Connect", "Network", "Protocol", "Read", "Remote")) or isinstance(exc, OSError):
                raise LLMError("connection", f"Network error: {name}: {_short(exc)}", retryable=True) from exc
            raise

        latency = time.perf_counter() - started
        meta = resp.usage_metadata
        usage = Usage(
            input_tokens=(getattr(meta, "prompt_token_count", 0) or 0) if meta else 0,
            output_tokens=((getattr(meta, "candidates_token_count", 0) or 0) + (getattr(meta, "thoughts_token_count", 0) or 0)) if meta else 0,
            cache_read_tokens=(getattr(meta, "cached_content_token_count", 0) or 0) if meta else 0,
        )
        block = getattr(getattr(resp, "prompt_feedback", None), "block_reason", None)
        if block:
            raise LLMError("refusal", f"The request was blocked: {getattr(block, 'name', block)}")
        candidates = resp.candidates or []
        finish = getattr(candidates[0], "finish_reason", None) if candidates else None
        finish_name = getattr(finish, "name", str(finish)) if finish else None
        if finish_name in _BLOCKED:
            raise LLMError("refusal", f"The model stopped with finish reason {finish_name}.")
        if finish_name == "MAX_TOKENS":
            raise LLMError("truncated", "Output hit max_output_tokens before the JSON was complete.")
        text = (resp.text or "").strip() if candidates else ""
        if not text:
            raise LLMError("bad_output", f"The response had no text (finish reason {finish_name}).")
        return LLMResult(data=_parse_json(text), usage=usage, model=model, latency_s=latency, stop_reason=finish_name)


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError("bad_output", f"The reply was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("bad_output", "The reply was JSON but not an object.")
    return data


_DAILY = re.compile(r"per ?day|daily|limit:\s*0\b", re.IGNORECASE)


def _map_client_error(exc: Exception) -> LLMError:
    code = getattr(exc, "code", 0) or 0
    message = _short(exc)
    if code == 429:
        if _DAILY.search(str(exc)):
            # Waiting a few seconds cannot fix an exhausted daily allowance (free tier: a small number of
            # requests per day for the stronger models), so do not retry. The pipeline falls back instead.
            return LLMError(
                "quota",
                "Daily quota exhausted for this model (429). It resets at midnight Pacific time. "
                f"Use another model or key. Details: {message}",
            )
        return LLMError("rate_limit", f"Rate limited (429): {message}", retryable=True, retry_after=_retry_delay(exc))
    if code == 408:
        return LLMError("timeout", "Request timed out (408)", retryable=True)
    if code in (401, 403):
        return LLMError("auth", f"Authentication or permission error ({code}): {message}")
    if code == 404:
        return LLMError("bad_request", f"Not found (404). The model name may be unavailable to your account: {message}")
    return LLMError("bad_request", f"Bad request ({code}): {message}")


def _retry_delay(exc: Exception) -> Optional[float]:
    """Google puts a suggested wait like 'retryDelay': '34s' in the error details."""
    try:
        match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?([\d.]+)s", json.dumps(getattr(exc, "details", None) or str(exc)))
        return float(match.group(1)) if match else None
    except Exception:
        return None


def _short(exc: Exception, limit: int = 300) -> str:
    return str(exc).replace("\n", " ")[:limit]


def make_client(settings: Settings) -> LLMClient:
    if settings.provider == "gemini":
        return GeminiClient(settings, base_url=os.getenv("GEMINI_BASE_URL") or None)
    raise ValueError(
        f"Unknown provider {settings.provider!r}. Only 'gemini' is implemented; "
        "add a class with the same extract() signature to support another."
    )


# --------------------------------------------------------------------------- #
# Retries for transient errors
# --------------------------------------------------------------------------- #
def call_with_retries(
    fn: Callable[[], T],
    *,
    attempts: int,
    backoff_s: float,
    sleep: Callable[[float], None] = time.sleep,
    max_delay_s: float = 60.0,
    label: str = "",
) -> tuple[T, int]:
    """Run fn, retrying only retryable LLMErrors with exponential backoff and jitter.

    Returns (result, retries_used). Raises the last LLMError when attempts run out or the
    error is not retryable (auth, bad request, refusal, truncation).
    """
    retries = 0
    for attempt in range(max(attempts, 1)):
        try:
            return fn(), retries
        except LLMError as exc:
            last_attempt = attempt >= attempts - 1
            if not exc.retryable or last_attempt:
                raise
            delay = backoff_s * (2**attempt) + random.uniform(0, 0.25 * backoff_s)
            if exc.retry_after is not None:
                delay = max(delay, exc.retry_after)
            delay = min(delay, max_delay_s)
            # Visible on stderr (logging's default handler), so a slow retry never looks like a frozen run.
            log.warning("%s: %s, retry %d of %d in %.0fs", label or "API call", exc.kind, attempt + 1, attempts - 1, delay)
            sleep(delay)
            retries += 1
    raise AssertionError("unreachable")  # pragma: no cover
