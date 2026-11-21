"""Token cost accounting. Prices live in pricing.json so they can be re-checked without code changes."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from .config import ROOT
from .llm import Usage

PRICING_PATH = ROOT / "pricing.json"


@lru_cache(maxsize=1)
def load_pricing() -> dict:
    with open(PRICING_PATH, encoding="utf-8") as fh:
        return json.load(fh)["models"]


def cost_usd(model: str, usage: Usage, pricing: Optional[dict] = None) -> Optional[float]:
    """Dollar cost of one API call, or None when the model has no entry in pricing.json.

    cost = input_tokens * input_price + output_tokens * output_price   (prices are per million tokens)
    Cache reads and writes, when present, are billed at the usual multipliers of the input price.
    """
    table = pricing if pricing is not None else load_pricing()
    rates = table.get(model)
    if not rates:
        return None
    prompt_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    long_prompt = prompt_tokens > rates.get("long_prompt_threshold", float("inf"))
    in_rate = rates["input_long"] if long_prompt and "input_long" in rates else rates["input"]
    out_rate = rates["output_long"] if long_prompt and "output_long" in rates else rates["output"]
    total = (
        usage.input_tokens * in_rate
        + usage.cache_read_tokens * rates.get("cache_read", 0.1 * in_rate)
        + usage.cache_write_tokens * rates.get("cache_write", 1.25 * in_rate)
        + usage.output_tokens * out_rate
    ) / 1_000_000
    return round(total, 8)
