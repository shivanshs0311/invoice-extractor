"""Matching rules for the eval harness. These are the rules stated in REPORT.md.

Philosophy: be strict about facts that finance would act on (numbers, dates, identifiers, currency)
and tolerant about formatting that does not change meaning (case, punctuation, legal suffixes).

| field          | rule                                                                                     |
|----------------|------------------------------------------------------------------------------------------|
| is_invoice     | exact boolean                                                                            |
| vendor         | normalise (case, accents, punctuation, "&"->"and", drop legal suffixes like Pvt/Ltd/LLC); |
|                | match if equal, or one name's tokens are a subset of the other's, or similarity >= 0.88   |
| invoice_number | case-insensitive, ignoring spaces and punctuation ("INV-2041" == "inv 2041")             |
| invoice_date   | exact ISO date after parsing                                                             |
| currency       | exact ISO code, symbols mapped first (Rs/rupee->INR, $->USD, euro->EUR, pound->GBP)       |
| tax_total      | numeric, |a-b| <= 0.01; the pack README says no tax is 0, so null does NOT match 0         |
| total          | numeric, |a-b| <= 0.01; null only matches null                                           |
| line_items     | per-item matching, see match_line_items                                                  |
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Optional

from .schema import coerce_number

MONEY_TOL = 0.01
QTY_TOL = 1e-6
VENDOR_SIMILARITY = 0.88
DESCRIPTION_SIMILARITY = 0.6

LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "incorporated", "corp", "corporation", "co",
    "company", "gmbh", "plc", "pte", "sa", "bv", "ag", "oy", "opc", "lp", "the",
}
CURRENCY_ALIASES = {
    "RS": "INR", "RS.": "INR", "\u20b9": "INR", "INR": "INR", "RUPEES": "INR", "RUPEE": "INR",
    "$": "USD", "US$": "USD", "\u20ac": "EUR", "\u00a3": "GBP",
}


# --------------------------------------------------------------------------- #
# Normalisers
# --------------------------------------------------------------------------- #
def norm_text(value: Any) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def norm_vendor(value: Any) -> str:
    tokens = [t for t in norm_text(value).split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def norm_id(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).upper()


def norm_currency(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    return CURRENCY_ALIASES.get(s, s) or None


def to_date(value: Any) -> Optional[date | str]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return str(value).strip()  # unparseable labels fall back to exact string comparison


def to_num(value: Any) -> Optional[float]:
    try:
        return coerce_number(value)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Scalar field matchers (each returns True/False)
# --------------------------------------------------------------------------- #
def match_bool(pred: Any, gt: Any) -> bool:
    return pred is not None and bool(pred) == bool(gt)


def match_vendor(pred: Any, gt: Any) -> bool:
    if pred is None and gt is None:
        return True
    if pred is None or gt is None:
        return False
    a, b = norm_vendor(pred), norm_vendor(gt)
    if not a or not b:
        return norm_text(pred) == norm_text(gt)
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:
        return True
    return SequenceMatcher(None, a, b).ratio() >= VENDOR_SIMILARITY


def match_id(pred: Any, gt: Any) -> bool:
    if pred is None and gt is None:
        return True
    if pred is None or gt is None:
        return False
    return norm_id(pred) == norm_id(gt)


def match_date(pred: Any, gt: Any) -> bool:
    return to_date(pred) == to_date(gt)


def match_currency(pred: Any, gt: Any) -> bool:
    return norm_currency(pred) == norm_currency(gt)


def match_money(pred: Any, gt: Any, *, none_is_zero: bool = False) -> bool:
    a, b = to_num(pred), to_num(gt)
    if none_is_zero:
        a, b = (0.0 if a is None else a), (0.0 if b is None else b)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= MONEY_TOL


def match_tax(pred: Any, gt: Any) -> bool:
    """The pack README says zero tax or no tax at all is 0, so null is a different answer from 0."""
    return match_money(pred, gt)


# --------------------------------------------------------------------------- #
# Line items
# --------------------------------------------------------------------------- #
def description_similarity(a: Any, b: Any) -> float:
    na, nb = norm_text(a), norm_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _qty_ok(pred_qty: Any, gt_qty: Any) -> bool:
    g = to_num(gt_qty)
    if g is None:
        return True  # ground truth has no quantity: do not penalise whatever we returned
    p = to_num(pred_qty)
    return p is not None and abs(p - g) <= QTY_TOL


@dataclass
class LineItemScore:
    n_pred: int
    n_gt: int
    matched: int
    amount_matched: int
    precision: float
    recall: float
    f1: float
    amount_f1: float
    strict: bool


def _f1(matched: int, n_pred: int, n_gt: int) -> tuple[float, float, float]:
    if n_pred == 0 and n_gt == 0:
        return 1.0, 1.0, 1.0
    precision = matched / n_pred if n_pred else 0.0
    recall = matched / n_gt if n_gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _greedy_match(pred: list[dict], gt: list[dict], ok) -> int:
    """One-to-one greedy matching; prefers the most similar description first."""
    pairs = []
    for i, p in enumerate(pred):
        for j, g in enumerate(gt):
            if ok(p, g):
                pairs.append((-description_similarity(p.get("description"), g.get("description")), i, j))
    pairs.sort()
    used_p: set[int] = set()
    used_g: set[int] = set()
    for _, i, j in pairs:
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
    return len(used_p)


def match_line_items(pred: Optional[list[dict]], gt: Optional[list[dict]]) -> LineItemScore:
    """An item matches when amount is within 0.01, quantity agrees (if the label has one), and the
    description similarity is >= 0.6. Reports item-level F1, an amount-only F1 (ignores wording, so
    it isolates number errors from description-style differences), and a strict all-or-nothing flag."""
    pred = pred or []
    gt = gt or []

    def full(p: dict, g: dict) -> bool:
        return (
            match_money(p.get("amount"), g.get("amount"))
            and _qty_ok(p.get("quantity"), g.get("quantity"))
            and description_similarity(p.get("description"), g.get("description")) >= DESCRIPTION_SIMILARITY
        )

    def amount_only(p: dict, g: dict) -> bool:
        return match_money(p.get("amount"), g.get("amount"))

    matched = _greedy_match(pred, gt, full)
    amount_matched = _greedy_match(pred, gt, amount_only)
    precision, recall, f1 = _f1(matched, len(pred), len(gt))
    _, _, amount_f1 = _f1(amount_matched, len(pred), len(gt))
    strict = len(pred) == len(gt) == matched
    return LineItemScore(len(pred), len(gt), matched, amount_matched, precision, recall, f1, amount_f1, strict)
