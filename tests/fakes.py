"""Test doubles and helpers."""
from __future__ import annotations

import copy

from invoice_extractor.llm import LLMError, LLMResult, Usage


class FakeClient:
    """handler(call_number, model, content) -> dict payload | (payload, Usage) | Exception."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def extract(self, *, model, system, content, tool_schema, max_tokens):
        self.calls.append({"model": model, "content": content, "max_tokens": max_tokens, "system": system})
        out = self.handler(len(self.calls), model, content)
        if isinstance(out, Exception):
            raise out
        payload, usage = out if isinstance(out, tuple) else (out, Usage(1000, 200))
        return LLMResult(data=copy.deepcopy(payload), usage=usage, model=model, latency_s=0.01, stop_reason="STOP")


def invoice_payload(**over) -> dict:
    base = {
        "document_type": "invoice",
        "is_invoice": True,
        "vendor": "Sharma Office Supplies Pvt Ltd",
        "invoice_number": "SOS/2026/0412",
        "invoice_date": "2026-03-14",
        "currency": "INR",
        "line_items": [
            {"description": "A4 paper, 500 sheets", "quantity": 10, "amount": 3200.0},
            {"description": "Laser printer toner", "quantity": 3, "amount": 14550.0},
        ],
        "tax_total": 3196.0,
        "total": 20946.0,
        "legibility": "good",
        "confidence": 0.95,
        "notes": None,
    }
    base.update(over)
    return base


def good_payload(**over) -> dict:
    """A correct reading of the invoice that tests/factories.py draws: two items, no tax, total 17750."""
    return invoice_payload(**{"tax_total": 0.0, "total": 17750.0, **over})


def timeout_error():
    return LLMError("timeout", "timed out", retryable=True)
