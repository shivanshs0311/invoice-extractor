"""Every deliverable JSON must validate against the assignment's own schema.json (it forbids extra keys)."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from factories import digital_pdf, garbage_pdf
from fakes import FakeClient, good_payload, invoice_payload
from invoice_extractor.config import Settings
from invoice_extractor.pipeline import extract_document

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
S = Settings(api_backoff_s=0.0)
NOTHING = {"vendor": None, "invoice_number": None, "invoice_date": None, "currency": None,
           "line_items": None, "tax_total": None, "total": None}


def errors(obj):
    return [e.message for e in VALIDATOR.iter_errors(obj)]


def test_an_invoice_output_validates(tmp_path):
    res = extract_document(digital_pdf(tmp_path / "a.pdf"), S, FakeClient(lambda n, m, c: good_payload()))
    assert errors(res.public_json()) == [], res.public_json()


def test_a_non_invoice_output_validates(tmp_path):
    payload = invoice_payload(document_type="bank_statement", is_invoice=False, **NOTHING)
    res = extract_document(digital_pdf(tmp_path / "a.pdf"), S, FakeClient(lambda n, m, c: payload))
    assert res.public_json()["is_invoice"] is False and errors(res.public_json()) == []


def test_review_flags_are_outside_the_schema_by_design(tmp_path):
    res = extract_document(digital_pdf(tmp_path / "a.pdf"), S, FakeClient(lambda n, m, c: good_payload()))
    assert errors(res.public_json()) == []
    assert any("additional properties" in m.lower() for m in errors(res.public_json(with_review=True)))


def test_failed_records_are_deliberately_not_schema_valid(tmp_path):
    res = extract_document(garbage_pdf(tmp_path / "g.pdf"), S, None)
    out = res.public_json()
    assert out["is_invoice"] is None and out["error"]["code"] == "corrupt_file"
    assert errors(out)  # null is_invoice and an error key: must never pass as a real "not an invoice"


def test_schema_rejects_a_non_invoice_with_values():
    bad = {"is_invoice": False, "vendor": "x", "invoice_number": None, "invoice_date": None, "currency": None,
           "line_items": None, "tax_total": None, "total": None}
    assert errors(bad)
