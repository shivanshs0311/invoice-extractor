from datetime import date

from invoice_extractor.config import Settings
from invoice_extractor.schema import Extraction
from invoice_extractor.validate import check_totals, feedback_for_checks, is_unreadable, parse_extraction, run_checks
from fakes import invoice_payload

S = Settings()


def ext(**over):
    return Extraction.model_validate(invoice_payload(**over))


def names(report):
    return {c.name for c in report.failing}


def test_clean_invoice_passes_everything():
    report = run_checks(ext(), S)
    assert report.passed and not report.failing


def test_totals_mismatch_is_an_error():
    report = run_checks(ext(total=21946.0), S)
    assert not report.passed
    assert "totals_reconcile" in names(report)
    assert "difference=1000.00" in next(c for c in report.errors if c.name == "totals_reconcile").detail


def test_totals_tolerance_covers_rounding():
    assert check_totals(ext(total=20946.6), 1.0).ok
    assert not check_totals(ext(total=20948.5), 1.0).ok


def test_null_tax_is_treated_as_zero_by_the_totals_check():
    e = ext(tax_total=None, total=17750.0)
    assert check_totals(e, 1.0).ok


def test_normalise_tax_only_fires_when_items_equal_total():
    from invoice_extractor.validate import normalise_tax
    fixed, notes = normalise_tax(ext(tax_total=None, total=17750.0), 1.0)
    assert fixed.tax_total == 0.0 and notes
    same, notes = normalise_tax(ext(tax_total=None, total=20946.0), 1.0)
    assert same.tax_total is None and not notes
    same, notes = normalise_tax(ext(tax_total=5.0, total=17755.0), 1.0)
    assert same.tax_total == 5.0 and not notes


def test_totals_unverifiable_is_a_warning_not_an_error():
    report = run_checks(ext(line_items=None), S)
    assert "core_fields_present" in names(report)  # missing line items is an error
    c = check_totals(ext(total=None), 1.0)
    assert c.name == "totals_unverifiable" and c.severity == "warn"


def test_missing_core_field_is_an_error():
    report = run_checks(ext(invoice_number=None), S)
    assert [c.name for c in report.errors] == ["core_fields_present"]


def test_doc_type_mismatch_is_an_error():
    report = run_checks(ext(document_type="purchase_order"), S)
    assert "document_type_consistent" in {c.name for c in report.errors}


def test_warnings_flag_review_without_retry():
    report = run_checks(ext(legibility="poor", confidence=0.4), S)
    assert report.passed  # nothing to retry
    assert {"legibility_good", "confidence_ok"} <= set(report.review_reasons)


def test_future_and_ancient_dates_warn():
    assert "date_plausible" in names(run_checks(ext(invoice_date="2031-01-01"), S, today=date(2026, 11, 21)))
    assert "date_plausible" in names(run_checks(ext(invoice_date="1980-01-01"), S))


def test_unknown_currency_and_input_warnings():
    assert "currency_known" in names(run_checks(ext(currency="ZZZ"), S))
    assert "input_quality_ok" in names(run_checks(ext(), S, source_warnings=["truncated_pages"]))


def test_non_invoice_with_values_warns():
    report = run_checks(ext(document_type="bank_statement", is_invoice=False), S)
    assert "non_invoice_fields_null" in names(report)


def test_parse_extraction_reports_readable_problems():
    parsed, problems = parse_extraction({"document_type": "invoice"})
    assert parsed is None and any("is_invoice" in p for p in problems)
    assert parse_extraction("nope")[0] is None


def test_feedback_mentions_numbers():
    report = run_checks(ext(total=1.0), S)
    assert "sum(line amounts)" in feedback_for_checks(report)


# --- unreadable documents ----------------------------------------------------
def _unreadable(**over):
    e = ext(**over)
    return is_unreadable(e, run_checks(e, S), S)


def test_good_and_fair_scans_are_never_unreadable():
    assert not _unreadable(legibility="good", confidence=0.1)
    assert not _unreadable(legibility="fair", confidence=0.1, is_invoice=False, document_type="other")


def test_a_poor_scan_that_is_a_confident_consistent_invoice_is_kept():
    assert not _unreadable(legibility="poor", confidence=0.9)


def test_a_poor_scan_that_says_not_an_invoice_is_unreadable():
    assert _unreadable(legibility="poor", confidence=0.95, is_invoice=False, document_type="other", vendor=None, invoice_number=None,
                       invoice_date=None, currency=None, line_items=None, tax_total=None, total=None)


def test_a_poor_scan_with_low_confidence_or_a_failed_error_check_is_unreadable():
    assert _unreadable(legibility="poor", confidence=0.4)
    assert _unreadable(legibility="poor", confidence=0.95, total=1.0)


def test_default_tolerance_is_tight_enough_to_catch_a_misread_digit():
    # stress test: tax read as 19688.8 instead of 19689.6 (0.80 off) must not pass
    assert S.total_tolerance == 0.05
    assert run_checks(ext(), S).passed
    assert not run_checks(ext(total=20946.8), S).passed  # 0.80 off
    assert run_checks(ext(total=20946.03), S).passed  # cent rounding is fine
