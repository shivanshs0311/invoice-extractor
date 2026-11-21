import pytest
from PIL import Image

from factories import digital_pdf, garbage_pdf, locked_pdf, photo_jpg, scanned_pdf
from fakes import FakeClient, good_payload, invoice_payload, timeout_error
from invoice_extractor.config import Settings
from invoice_extractor.ingest import load_document
from invoice_extractor.llm import LLMError
from invoice_extractor.pipeline import extract_document, extract_many, plan_steps

S = Settings(api_backoff_s=0.0, api_attempts=3)
EIGHT = ["is_invoice", "vendor", "invoice_number", "invoice_date", "currency", "line_items", "tax_total", "total"]


@pytest.fixture()
def pdf(tmp_path):
    return digital_pdf(tmp_path / "inv.pdf")


def test_happy_path_uses_the_cheap_text_route_once(pdf):
    client = FakeClient(lambda n, m, c: good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and res.output["needs_review"] is False
    assert len(client.calls) == 1 and client.calls[0]["model"] == S.model
    assert any("TEXT LAYER" in p.get("text", "") for p in client.calls[0]["content"])
    assert not any(p["type"] == "image" for p in client.calls[0]["content"])
    assert res.output["total"] == 17750.0 and res.output["invoice_date"] == "2026-03-14"
    assert res.meta["cost_usd"] == pytest.approx(0.0008)  # 1000 in x $0.30/M + 200 out x $2.50/M
    assert res.meta["input_tokens"] == 1000 and res.meta["output_tokens"] == 200


def test_totals_mismatch_retries_on_the_stronger_model_with_images_and_feedback(pdf):
    bad = good_payload(total=18750.0)
    client = FakeClient(lambda n, m, c: bad if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and len(client.calls) == 2
    second = client.calls[1]
    assert second["model"] == S.escalation_model
    assert any(p["type"] == "image" for p in second["content"])  # text plus images on the retry
    assert any("rejected by automatic checks" in p.get("text", "") for p in second["content"])
    assert any("totals_reconcile" in p.get("text", "") for p in second["content"])
    assert res.meta["final_mode"] == "hybrid" and res.meta["model"] == S.escalation_model
    assert res.meta["cost_usd"] > 0.0008  # both attempts are billed


def test_a_persistent_mismatch_is_flagged_not_hidden(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: good_payload(total=1.0)))
    assert res.status == "needs_review" and res.output["needs_review"] is True
    assert "totals_reconcile" in res.output["review_reasons"]
    assert res.output["total"] == 1.0  # the raw value is kept, but flagged


def test_schema_invalid_then_valid(pdf):
    client = FakeClient(lambda n, m, c: good_payload(invoice_date="14/03/2026") if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and res.meta["attempts"][0]["status"] == "schema_invalid"
    assert any("invoice_date" in p.get("text", "") for p in client.calls[1]["content"])


def test_output_that_never_matches_the_schema_is_a_failed_record(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: {"nonsense": 1}))
    assert res.status == "failed" and res.output["error"]["code"] == "invalid_output"
    assert res.output["is_invoice"] is None and res.output["needs_review"] is True


def test_a_transient_error_is_retried_without_escalating(pdf):
    client = FakeClient(lambda n, m, c: timeout_error() if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and len(client.calls) == 2
    assert res.meta["attempts"][0]["api_retries"] == 1
    assert all(call["model"] == S.model for call in client.calls)


def test_api_down_fails_gracefully(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: timeout_error()))
    assert res.status == "failed" and res.output["error"]["code"] == "api_timeout"
    assert res.output["needs_review"] is True


def test_a_connection_error_does_not_burn_the_second_model(pdf):
    client = FakeClient(lambda n, m, c: LLMError("connection", "no network", retryable=True))
    res = extract_document(pdf, S, client)
    assert res.status == "failed" and res.output["error"]["code"] == "api_connection"
    assert all(call["model"] == S.model for call in client.calls)


def test_an_auth_error_stops_immediately(pdf):
    client = FakeClient(lambda n, m, c: LLMError("auth", "bad key"))
    res = extract_document(pdf, S, client)
    assert res.status == "failed" and len(client.calls) == 1 and res.output["error"]["code"] == "api_auth"


def test_truncated_output_doubles_max_tokens(pdf):
    client = FakeClient(lambda n, m, c: LLMError("truncated", "cut") if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and client.calls[1]["max_tokens"] == 2 * client.calls[0]["max_tokens"]


def test_a_non_invoice_is_nulled_even_if_the_model_leaks_values(pdf):
    leaky = good_payload(document_type="purchase_order", is_invoice=False)
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: leaky))
    assert res.output["is_invoice"] is False
    assert all(res.output[k] is None for k in EIGHT[1:])
    assert "non_invoice_fields_null" in res.output["review_reasons"]


def test_a_clean_non_invoice_needs_no_review(pdf):
    empty = {"document_type": "bank_statement", "is_invoice": False, "vendor": None, "invoice_number": None,
             "invoice_date": None, "currency": None, "line_items": None, "tax_total": None, "total": None,
             "legibility": "good", "confidence": 0.9, "notes": None}
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: empty))
    assert res.status == "ok" and res.output["is_invoice"] is False and res.output["needs_review"] is False


def test_the_system_prompt_treats_the_document_as_data(pdf):
    client = FakeClient(lambda n, m, c: good_payload())
    extract_document(pdf, S, client)
    assert "untrusted data" in client.calls[0]["system"]


def test_a_document_type_contradiction_triggers_a_retry(pdf):
    client = FakeClient(lambda n, m, c: good_payload(document_type="purchase_order") if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert res.status == "ok" and len(client.calls) == 2


def test_scans_and_photos_go_straight_to_vision(tmp_path):
    for doc_path, source in ((scanned_pdf(tmp_path / "s.pdf"), "scanned_pdf"), (photo_jpg(tmp_path / "p.jpg"), "image")):
        client = FakeClient(lambda n, m, c: good_payload())
        res = extract_document(doc_path, S, client)
        assert res.status == "ok" and res.meta["source_type"] == source and res.meta["final_mode"] == "vision"
        content = client.calls[0]["content"]
        assert any(p["type"] == "image" for p in content) and not any("TEXT LAYER" in p.get("text", "") for p in content)


def test_bad_inputs_fail_gracefully_without_calling_the_api(tmp_path):
    (tmp_path / "empty.pdf").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("not a pdf", encoding="utf-8")
    Image.new("RGB", (900, 1200), (255, 255, 255)).save(tmp_path / "blank.png")
    garbage_pdf(tmp_path / "garbage.pdf")
    locked_pdf(tmp_path / "locked.pdf")
    expected = {"empty.pdf": "empty_file", "notes.txt": "unsupported_type", "blank.png": "blank_document",
                "garbage.pdf": "corrupt_file", "locked.pdf": "encrypted_pdf"}
    client = FakeClient(lambda n, m, c: pytest.fail("the API must not be called for a bad input"))
    for name, code in expected.items():
        res = extract_document(tmp_path / name, S, client)
        assert res.status == "failed" and res.output["needs_review"] is True, name
        assert res.output["error"]["code"] == code and res.meta["input_tokens"] == 0 and res.meta["cost_usd"] == 0
    assert client.calls == []


def test_a_bad_input_needs_no_api_key(tmp_path):
    res = extract_document(garbage_pdf(tmp_path / "g.pdf"), S, client=None)  # conftest removes GEMINI_API_KEY
    assert res.status == "failed" and res.output["error"]["code"] == "corrupt_file"


def test_a_missing_key_on_a_valid_document_is_a_loud_configuration_error(pdf):
    with pytest.raises(LLMError) as err:
        extract_document(pdf, S, client=None)
    assert "GEMINI_API_KEY" in str(err.value)


def test_an_unexpected_exception_is_contained(pdf):
    def boom(n, m, c):
        raise RuntimeError("boom")

    res = extract_document(pdf, S, FakeClient(boom))
    assert res.status == "failed" and res.output["error"]["code"] == "internal_error"


def test_default_output_is_exactly_the_eight_schema_fields_and_flags_are_opt_in(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: good_payload()))
    assert list(res.public_json()) == EIGHT
    assert list(res.public_json(with_review=True)) == EIGHT + ["needs_review", "review_reasons"]


def test_a_failed_record_always_carries_its_error(tmp_path):
    res = extract_document(garbage_pdf(tmp_path / "g.pdf"), S, None)
    assert res.public_json()["error"]["code"] == "corrupt_file" and res.public_json()["is_invoice"] is None


def test_missing_tax_is_recorded_as_zero_when_items_add_up(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: good_payload(tax_total=None)))
    assert res.output["tax_total"] == 0.0 and res.status == "ok"
    assert "tax_total set to 0" in res.meta["normalisations"][0]


def test_null_tax_is_not_invented_when_totals_do_not_add_up(pdf):
    res = extract_document(pdf, S, FakeClient(lambda n, m, c: good_payload(tax_total=None, total=18750.0)))
    assert res.output["tax_total"] is None and res.status == "needs_review"


def test_plan_steps_cascade_and_forced_modes(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf"), S)
    assert [s.mode for s in plan_steps(doc, S)] == ["text", "hybrid"]
    assert [s.mode for s in plan_steps(doc, S.with_overrides(mode="vision", escalate=False))] == ["vision"]
    scan = load_document(photo_jpg(tmp_path / "p.jpg"), S)
    assert [s.mode for s in plan_steps(scan, S.with_overrides(mode="text"))] == ["vision", "vision"]  # nothing to read as text


def test_extract_many_keeps_order_and_survives_bad_files(tmp_path):
    paths = [digital_pdf(tmp_path / "a.pdf"), garbage_pdf(tmp_path / "g.pdf"), digital_pdf(tmp_path / "b.pdf")]
    results = extract_many(paths, S, FakeClient(lambda n, m, c: good_payload()), workers=3)
    assert [r.status for r in results] == ["ok", "failed", "ok"]


# --- the stronger model is not always available (free tier: a small daily quota) ------------------------------
def _quota():
    return LLMError("quota", "daily quota exhausted")


def test_when_the_strong_model_has_no_quota_the_retry_runs_on_the_first_pass_model(pdf):
    def handler(n, model, content):
        if n == 1:
            return good_payload(total=18750.0)  # fails the totals check
        return _quota() if model == S.escalation_model else good_payload()

    client = FakeClient(handler)
    res = extract_document(pdf, S, client)
    assert [c["model"] for c in client.calls] == [S.model, S.escalation_model, S.model]
    assert res.status == "ok" and res.meta["model"] == S.model
    assert [a["status"] for a in res.meta["attempts"]] == ["checks_failed", "api_error", "ok"]
    third = client.calls[2]["content"]
    assert any("rejected by automatic checks" in p.get("text", "") for p in third)  # the feedback survived
    assert any(p["type"] == "image" for p in third)  # and the page images are still added


def test_the_fallback_happens_once_and_a_bad_read_stays_flagged(pdf):
    client = FakeClient(lambda n, m, c: _quota() if m == S.escalation_model else good_payload(total=1.0))
    res = extract_document(pdf, S, client)
    assert len(client.calls) == 3
    assert res.status == "needs_review" and "totals_reconcile" in res.output["review_reasons"]


def test_a_quota_error_on_the_first_pass_goes_straight_to_the_second_model(pdf):
    client = FakeClient(lambda n, m, c: _quota() if n == 1 else good_payload())
    res = extract_document(pdf, S, client)
    assert [c["model"] for c in client.calls] == [S.model, S.escalation_model]
    assert res.status == "ok" and res.meta["model"] == S.escalation_model


def test_no_fallback_when_both_models_are_the_same(pdf):
    same = S.with_overrides(escalation_model=S.model)
    client = FakeClient(lambda n, m, c: _quota())
    res = extract_document(pdf, same, client)
    assert len(client.calls) == 2 and res.status == "failed" and res.output["error"]["code"] == "api_quota"


def test_a_quota_error_is_not_retried_with_backoff(pdf):
    client = FakeClient(lambda n, m, c: _quota())
    res = extract_document(pdf, S, client)
    assert len(client.calls) == 2  # one per model, no api retries
    assert all(a["api_retries"] == 0 for a in res.meta["attempts"])


def test_ctrl_c_during_a_batch_stops_cleanly(tmp_path):
    paths = [digital_pdf(tmp_path / f"{i}.pdf") for i in range(4)]

    def stop(i, path, res):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        extract_many(paths, S, FakeClient(lambda n, m, c: good_payload()), workers=1, progress=stop)


# --- unreadable scans --------------------------------------------------------
NOTHING = {"vendor": None, "invoice_number": None, "invoice_date": None, "currency": None,
           "line_items": None, "tax_total": None, "total": None}


def test_a_poor_scan_read_as_not_an_invoice_is_an_explicit_failed_record(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf")
    payload = invoice_payload(document_type="other", is_invoice=False, legibility="poor", confidence=0.9, **NOTHING)
    res = extract_document(scan, S, FakeClient(lambda n, m, c: payload))
    assert res.status == "failed" and res.output["error"]["code"] == "unreadable_document"
    assert res.output["is_invoice"] is None  # unknown, not False
    assert res.output["needs_review"] is True and res.output["review_reasons"] == ["extraction_failed:unreadable_document"]
    assert res.meta["legibility"] == "poor" and res.meta["input_tokens"] > 0  # the attempt is still billed and logged
    assert "error" in res.public_json()


def test_a_poor_scan_with_invented_low_confidence_values_is_also_unreadable(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf")
    res = extract_document(scan, S, FakeClient(lambda n, m, c: good_payload(legibility="poor", confidence=0.4)))
    assert res.status == "failed" and res.output["error"]["code"] == "unreadable_document"
    assert res.output["vendor"] is None and res.output["total"] is None


def test_a_poor_scan_that_still_reads_as_a_confident_consistent_invoice_is_kept_and_flagged(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf")
    res = extract_document(scan, S, FakeClient(lambda n, m, c: good_payload(legibility="poor", confidence=0.9)))
    assert res.status == "needs_review" and res.output["total"] == 17750.0
    assert "legibility_good" in res.output["review_reasons"]


def test_a_fair_scan_that_says_not_an_invoice_is_still_a_normal_non_invoice(tmp_path):
    scan = scanned_pdf(tmp_path / "scan.pdf")
    payload = invoice_payload(document_type="bank_statement", is_invoice=False, legibility="fair", confidence=0.9, **NOTHING)
    res = extract_document(scan, S, FakeClient(lambda n, m, c: payload))
    assert res.output["is_invoice"] is False and not res.output.get("error")
