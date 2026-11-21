import pytest

from invoice_extractor.matching import (
    match_bool, match_currency, match_date, match_id, match_line_items, match_money, match_tax, match_vendor,
)


@pytest.mark.parametrize(
    "pred,gt,ok",
    [
        ("Acme Pvt Ltd", "Acme", True),
        ("ACME SUPPLIES PRIVATE LIMITED", "Acme Supplies Pvt. Ltd.", True),
        ("Penny & Co Stationery", "Penny and Co Stationery", True),
        ("Acme Supplies", "Acme", True),
        ("Nordlicht Werkzeug GmbH", "Nordlicht Werkzeug", True),
        ("Tandon Traders", "Sharma Office Supplies", False),
        (None, None, True),
        (None, "Acme", False),
        ("Acme", None, False),
    ],
)
def test_vendor(pred, gt, ok):
    assert match_vendor(pred, gt) is ok


@pytest.mark.parametrize(
    "pred,gt,ok",
    [("INV-2041", "inv 2041", True), ("INV2041", "INV-2041", True), ("INV-2041", "INV-2014", False), ("0042", "42", False), (None, None, True)],
)
def test_invoice_number(pred, gt, ok):
    assert match_id(pred, gt) is ok


@pytest.mark.parametrize(
    "pred,gt,ok",
    [("1,200.00", 1200, True), (1200.004, 1200, True), (1200.5, 1200, False), (None, 5, False), (None, None, True)],
)
def test_money(pred, gt, ok):
    assert match_money(pred, gt) is ok


def test_tax_null_is_not_zero_because_the_pack_says_no_tax_is_zero():
    assert match_tax(0.0, 0)
    assert not match_tax(None, 0)
    assert not match_tax(0.0, None)
    assert match_tax(None, None)
    assert not match_tax(None, 12.5)
    assert not match_money(None, 0)


def test_dates_and_currency_and_bool():
    assert match_date("2026-03-14", "2026-03-14")
    assert not match_date("2026-03-04", "2026-04-03")
    assert match_date(None, None) and not match_date(None, "2026-03-14")
    assert match_currency("Rs", "INR") and match_currency("inr", "INR") and not match_currency("USD", "INR")
    assert match_bool(False, False) and not match_bool(None, False) and not match_bool(True, False)


def item(d, q, a):
    return {"description": d, "quantity": q, "amount": a}


def test_line_items_perfect_and_wording_tolerance():
    gt = [item("A4 paper, 500 sheets", 10, 3200.0), item("Toner", 3, 14550.0)]
    pred = [item("A4 Paper 500 sheets", 10, 3200), item("Laser printer toner", 3, 14550.0)]
    s = match_line_items(pred, gt)
    assert s.strict and s.f1 == 1.0


def test_line_items_missing_and_extra():
    gt = [item("A", 1, 10.0), item("B", 1, 20.0), item("C", 1, 30.0)]
    s = match_line_items([item("A", 1, 10.0), item("B", 1, 20.0)], gt)
    assert not s.strict and s.matched == 2 and round(s.recall, 2) == 0.67 and s.precision == 1.0
    s = match_line_items(gt + [item("D", 1, 5.0)], gt)
    assert not s.strict and s.precision == 0.75 and s.recall == 1.0


def test_line_items_amount_only_isolates_wording_errors():
    gt = [item("Widget blue", 2, 50.0)]
    pred = [item("Completely different words", 2, 50.0)]
    s = match_line_items(pred, gt)
    assert s.f1 == 0.0 and s.amount_f1 == 1.0


def test_line_items_wrong_quantity_fails_when_label_has_quantity():
    assert not match_line_items([item("A", 2, 10.0)], [item("A", 1, 10.0)]).strict
    assert match_line_items([item("A", 2, 10.0)], [item("A", None, 10.0)]).strict


def test_line_items_both_empty_is_perfect():
    assert match_line_items(None, None).strict
    assert match_line_items([], None).f1 == 1.0
    assert not match_line_items([item("A", 1, 1.0)], None).strict
