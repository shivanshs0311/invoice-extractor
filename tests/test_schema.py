import pytest
from pydantic import ValidationError

from invoice_extractor.schema import (
    EXTRACTION_TOOL_SCHEMA,
    Extraction,
    Invoice,
    LineItem,
    coerce_number,
)
from fakes import invoice_payload


def test_tool_schema_matches_extraction_model():
    assert set(EXTRACTION_TOOL_SCHEMA["properties"]) == set(Extraction.model_fields)
    assert set(EXTRACTION_TOOL_SCHEMA["required"]) == set(Extraction.model_fields)
    assert EXTRACTION_TOOL_SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize(
    "raw,expected",
    [(1200, 1200.0), ("1,200.00", 1200.0), ("1,23,456.50", 123456.5), ("(45.10)", -45.1), ("Rs. 99", 99.0), ("", None), (None, None)],
)
def test_coerce_number_ok(raw, expected):
    assert coerce_number(raw) == expected


@pytest.mark.parametrize("raw", ["1.234,56", "abc", True, float("nan"), [1]])
def test_coerce_number_rejects_ambiguous(raw):
    with pytest.raises(ValueError):
        coerce_number(raw)


def test_extraction_normalises_types():
    ext = Extraction.model_validate(invoice_payload(invoice_number=2041, currency="inr", vendor="  Acme   Ltd "))
    assert ext.invoice_number == "2041"
    assert ext.currency == "INR"
    assert ext.vendor == "Acme Ltd"


def test_bad_date_and_currency_rejected():
    with pytest.raises(ValidationError):
        Extraction.model_validate(invoice_payload(invoice_date="14/03/2026"))
    with pytest.raises(ValidationError):
        Extraction.model_validate(invoice_payload(currency="rupees"))


def test_non_invoice_public_model_forces_nulls():
    with pytest.raises(ValidationError):
        Invoice(is_invoice=False, vendor="Acme")
    ext = Extraction.model_validate(invoice_payload(document_type="purchase_order", is_invoice=False))
    out = Invoice.from_extraction(ext).to_json_dict()
    assert out == {
        "is_invoice": False, "vendor": None, "invoice_number": None, "invoice_date": None,
        "currency": None, "line_items": None, "tax_total": None, "total": None,
    }


def test_public_output_shape_and_key_order():
    out = Invoice.from_extraction(Extraction.model_validate(invoice_payload())).to_json_dict()
    assert list(out) == ["is_invoice", "vendor", "invoice_number", "invoice_date", "currency", "line_items", "tax_total", "total"]
    assert out["invoice_date"] == "2026-03-14"
    assert out["line_items"][0] == {"description": "A4 paper, 500 sheets", "quantity": 10, "amount": 3200.0}


def test_line_item_quantity_serialises_whole_numbers_as_int():
    assert LineItem(description="x", quantity=2.0, amount=1).model_dump()["quantity"] == 2
    assert LineItem(description="x", quantity=2.5, amount=1).model_dump()["quantity"] == 2.5
