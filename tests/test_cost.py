import pytest

from invoice_extractor.cost import cost_usd
from invoice_extractor.llm import Usage


def test_cost_is_tokens_times_price_per_million():
    # gemini-3.5-flash-lite: $0.30 in, $2.50 out per million tokens
    assert cost_usd("gemini-3.5-flash-lite", Usage(1000, 200)) == pytest.approx(0.0008)
    assert cost_usd("gemini-3.5-flash", Usage(1_000_000, 1_000_000)) == pytest.approx(1.5 + 9.0)


def test_thinking_tokens_are_part_of_output_tokens():
    assert cost_usd("gemini-3.5-flash-lite", Usage(0, 100 + 400)) == pytest.approx(500 * 2.5 / 1e6)


def test_unknown_model_has_no_price_instead_of_a_wrong_one():
    assert cost_usd("some-new-model", Usage(1000, 1000)) is None
