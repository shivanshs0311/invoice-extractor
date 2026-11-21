"""Validation: schema, internal consistency, and the totals reconciliation.

Each check has a severity:
* "error": the extraction is probably wrong. Triggers one retry on the escalation model, and if it
           still fails the document is flagged needs_review. Bad data is never passed on silently.
* "warn":  suspicious but not provably wrong. No retry, but the document is flagged needs_review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from pydantic import ValidationError

from .config import Settings
from .schema import INVOICE_ONLY_FIELDS, Extraction

CORE_FIELDS = ("vendor", "invoice_number", "invoice_date", "total")

KNOWN_CURRENCIES = {
    "INR", "USD", "EUR", "GBP", "AUD", "CAD", "SGD", "AED", "JPY", "CNY", "CHF", "SEK", "NOK", "DKK",
    "NZD", "HKD", "ZAR", "SAR", "QAR", "KWD", "BHD", "OMR", "MYR", "THB", "IDR", "PHP", "KRW", "BRL",
    "MXN", "RUB", "TRY", "PLN", "CZK", "HUF", "ILS", "EGP", "NGN", "KES", "BDT", "LKR", "NPR", "PKR",
}


@dataclass
class Check:
    name: str
    ok: bool
    severity: str  # "error" or "warn"
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def failing(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def errors(self) -> list[Check]:
        return [c for c in self.failing if c.severity == "error"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.failing if c.severity == "warn"]

    @property
    def passed(self) -> bool:
        """True when nothing needs a retry (warnings may still exist)."""
        return not self.errors

    @property
    def review_reasons(self) -> list[str]:
        return [c.name for c in self.failing]


# --------------------------------------------------------------------------- #
# Step 1: does the JSON parse and match the schema?
# --------------------------------------------------------------------------- #
def parse_extraction(raw: Any) -> tuple[Optional[Extraction], list[str]]:
    if not isinstance(raw, dict):
        return None, [f"output is {type(raw).__name__}, expected a JSON object"]
    try:
        return Extraction.model_validate(raw), []
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "(root)"
            problems.append(f"{loc}: {err['msg']}")
        return None, problems


# --------------------------------------------------------------------------- #
# Step 2: arithmetic and sanity checks
# --------------------------------------------------------------------------- #
def check_totals(ext: Extraction, tolerance: float) -> Check:
    """sum(line amounts) + tax_total must equal total, within an absolute tolerance."""
    if ext.total is None or not ext.line_items:
        return Check("totals_unverifiable", False, "warn", "need both a total and at least one line item to reconcile")
    subtotal = sum(item.amount for item in ext.line_items)
    tax = ext.tax_total or 0.0
    expected = subtotal + tax
    diff = abs(expected - ext.total)
    detail = (
        f"sum(line amounts)={subtotal:.2f} + tax_total={tax:.2f} = {expected:.2f}; "
        f"total={ext.total:.2f}; difference={diff:.2f}; tolerance={tolerance:.2f}"
    )
    return Check("totals_reconcile", diff <= tolerance, "error", detail)


def run_checks(
    ext: Extraction,
    settings: Settings,
    source_warnings: Optional[list[str]] = None,
    today: Optional[date] = None,
) -> ValidationReport:
    today = today or date.today()
    report = ValidationReport()
    add = report.checks.append

    consistent = ext.is_invoice == (ext.document_type == "invoice")
    add(
        Check(
            "document_type_consistent",
            consistent,
            "error",
            "" if consistent else f"is_invoice={ext.is_invoice} but document_type={ext.document_type}",
        )
    )

    if not ext.is_invoice:
        leftovers = [f for f in INVOICE_ONLY_FIELDS if getattr(ext, f) not in (None, [])]
        add(
            Check(
                "non_invoice_fields_null",
                not leftovers,
                "warn",
                "" if not leftovers else f"model returned values for a non-invoice, they were nulled: {leftovers}",
            )
        )
    else:
        missing = [f for f in CORE_FIELDS if getattr(ext, f) is None]
        if not ext.line_items:
            missing.append("line_items")
        add(Check("core_fields_present", not missing, "error", "" if not missing else f"missing: {missing}"))

        currency_ok = ext.currency is not None and ext.currency in KNOWN_CURRENCIES
        add(
            Check(
                "currency_known",
                currency_ok,
                "warn",
                "" if currency_ok else f"currency is {ext.currency!r}, not a recognised ISO 4217 code",
            )
        )

        if ext.invoice_date is not None:
            plausible = date(2000, 1, 1) <= ext.invoice_date <= today + timedelta(days=1)
            add(
                Check(
                    "date_plausible",
                    plausible,
                    "warn",
                    "" if plausible else f"invoice_date {ext.invoice_date} is outside 2000-01-01..today",
                )
            )

        if ext.tax_total is not None and ext.total is not None:
            sane = 0 <= ext.tax_total <= abs(ext.total)
            add(
                Check(
                    "tax_plausible",
                    sane,
                    "warn",
                    "" if sane else f"tax_total={ext.tax_total:.2f} looks wrong next to total={ext.total:.2f}",
                )
            )

        add(check_totals(ext, settings.total_tolerance))

    clear = ext.legibility == "good"
    add(Check("legibility_good", clear, "warn", "" if clear else f"model reports legibility={ext.legibility}"))
    confident = ext.confidence >= settings.min_confidence
    add(
        Check(
            "confidence_ok",
            confident,
            "warn",
            "" if confident else f"model confidence {ext.confidence:.2f} < {settings.min_confidence:.2f}",
        )
    )

    risky = [w for w in (source_warnings or []) if w in {"truncated_pages", "truncated_text", "low_resolution", "poor_text_layer", "repaired_pdf"}]
    add(Check("input_quality_ok", not risky, "warn", "" if not risky else f"input issues: {risky}"))
    return report


# --------------------------------------------------------------------------- #
# Unreadable documents
# --------------------------------------------------------------------------- #
def is_unreadable(ext: Extraction, report: ValidationReport, settings: Settings) -> bool:
    """True when the model says the scan is poor AND the result cannot be trusted.

    A poor scan can still give a correct, self-consistent invoice, so poor legibility alone is only a review
    flag. It becomes an unreadable-document failure when the result also says "not an invoice", fails an
    error-level check, or the model's own confidence is below the threshold. Without this rule an all-null
    "not an invoice" (or an invented invoice) from a bad scan would look exactly like a real answer in the
    output JSON, because the review flag does not travel with the 8 schema fields.
    """
    if ext.legibility != "poor":
        return False
    return (not ext.is_invoice) or bool(report.errors) or ext.confidence < settings.min_confidence


# --------------------------------------------------------------------------- #
# Convention normalisation
# --------------------------------------------------------------------------- #
def normalise_tax(ext: Extraction, tolerance: float) -> tuple[Extraction, list[str]]:
    """The labelling convention says an invoice with no tax has tax_total 0, not null.

    A model sometimes answers null for "no tax printed". When that is the case and the line items already
    add up to the total, tax really is zero, so we record 0 and say so. Anything else stays null and is
    caught by the normal checks.
    """
    if ext.is_invoice and ext.tax_total is None and ext.line_items and ext.total is not None:
        if abs(sum(item.amount for item in ext.line_items) - ext.total) <= tolerance:
            return ext.model_copy(update={"tax_total": 0.0}), ["tax_total set to 0: no tax printed and the line items add up to the total"]
    return ext, []


# --------------------------------------------------------------------------- #
# Feedback text for a retry
# --------------------------------------------------------------------------- #
def feedback_for_checks(report: ValidationReport) -> str:
    lines = []
    for check in report.errors:
        lines.append(f"- {check.name}: {check.detail}")
    if any(c.name == "totals_reconcile" for c in report.errors):
        lines.append(
            "- Common causes: a missed or extra line item, a discount or shipping row left out, a tax amount "
            "missing or double counted, a misread digit, or line amounts that already include tax."
        )
    return "\n".join(lines)


def feedback_for_schema(problems: list[str]) -> str:
    return "\n".join(f"- schema: {p}" for p in problems[:10])
