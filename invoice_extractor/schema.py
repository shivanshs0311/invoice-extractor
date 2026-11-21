"""Schemas.

Two layers on purpose:

* `Extraction`  is what the LLM returns. It has a few extra fields (document_type,
  legibility, confidence, notes) that we use for validation and review flags.
* `Invoice`     is the public output schema from the assignment. Extra fields are
  stripped, and the "non-invoice means everything else is null" rule is enforced.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

TOOL_NAME = "record_extraction"

DocType = Literal["invoice", "purchase_order", "quotation", "bank_statement", "cover_letter", "other"]
Legibility = Literal["good", "fair", "poor"]

# Fields that must be null when the document is not an invoice.
INVOICE_ONLY_FIELDS = ("vendor", "invoice_number", "invoice_date", "currency", "line_items", "tax_total", "total")
PUBLIC_FIELDS = ("is_invoice",) + INVOICE_ONLY_FIELDS

# --------------------------------------------------------------------------- #
# Coercion helpers
# --------------------------------------------------------------------------- #
_PLAIN_NUM = re.compile(r"^[-+]?\d+(\.\d+)?$")
_GROUPED_NUM = re.compile(r"^[-+]?\d{1,3}(,\d{2,3})+(\.\d+)?$")  # 1,234.56 and 1,23,456.78
_CURRENCY_NOISE = re.compile(r"[\s\u20b9$\u20ac\u00a3\u00a5]|INR|USD|EUR|GBP|Rs\.?", re.IGNORECASE)


def coerce_number(value: Any) -> Optional[float]:
    """Turn JSON numbers and plain numeric strings into float. Anything ambiguous raises.

    "1,200.00" -> 1200.0, "(45.10)" -> -45.1, "1.234,56" -> ValueError (ambiguous on purpose).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("number must be finite")
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        negative = s.startswith("(") and s.endswith(")")
        s = _CURRENCY_NOISE.sub("", s).strip("()")
        if _PLAIN_NUM.match(s) or _GROUPED_NUM.match(s):
            number = float(s.replace(",", ""))
            return -abs(number) if negative else number
        raise ValueError(f"not an unambiguous number: {value!r}")
    raise ValueError(f"expected a number, got {type(value).__name__}")


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected text, got a boolean")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError(f"expected text, got {type(value).__name__}")
    value = " ".join(value.split())
    return value or None


def _date_or_none(value: Any) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        return value.strip()
    return value


Num = Annotated[Optional[float], BeforeValidator(coerce_number)]
Text = Annotated[Optional[str], BeforeValidator(_text)]


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Num = None
    amount: Annotated[float, BeforeValidator(coerce_number)]

    @field_validator("description", mode="before")
    @classmethod
    def _clean_description(cls, v: Any) -> str:
        cleaned = _text(v)
        return cleaned if cleaned is not None else ""

    @field_serializer("quantity")
    def _ser_quantity(self, v: Optional[float]):
        if v is None:
            return None
        return int(v) if float(v).is_integer() else v

    @field_serializer("amount")
    def _ser_amount(self, v: float) -> float:
        return round(v, 2)


class Extraction(BaseModel):
    """What the LLM must return (validated strictly, then converted to `Invoice`)."""

    model_config = ConfigDict(extra="ignore")

    document_type: DocType
    is_invoice: bool
    vendor: Text = None
    invoice_number: Text = None
    invoice_date: Annotated[Optional[date], BeforeValidator(_date_or_none)] = None
    currency: Text = None
    line_items: Optional[list[LineItem]] = None
    tax_total: Num = None
    total: Num = None
    legibility: Legibility = "good"
    confidence: float = 1.0
    notes: Text = None

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        code = v.upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError(f"currency must be a 3-letter ISO 4217 code, got {v!r}")
        return code

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            return 0.0
        return min(max(v, 0.0), 1.0)


class Invoice(BaseModel):
    """The public output schema from the assignment."""

    model_config = ConfigDict(extra="forbid")

    is_invoice: bool
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    currency: Optional[str] = None
    line_items: Optional[list[LineItem]] = None
    tax_total: Optional[float] = None
    total: Optional[float] = None

    @model_validator(mode="after")
    def _non_invoice_means_null(self) -> "Invoice":
        if not self.is_invoice:
            leftovers = [f for f in INVOICE_ONLY_FIELDS if getattr(self, f) is not None]
            if leftovers:
                raise ValueError(f"is_invoice is false but these fields are not null: {leftovers}")
        return self

    @field_serializer("tax_total", "total")
    def _ser_money(self, v: Optional[float]) -> Optional[float]:
        return None if v is None else round(v, 2)

    @classmethod
    def from_extraction(cls, ext: Extraction) -> "Invoice":
        if not ext.is_invoice:
            return cls(is_invoice=False)
        return cls(**{name: getattr(ext, name) for name in PUBLIC_FIELDS})

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")


def null_invoice_dict() -> dict:
    """All-null record used when extraction fails completely (is_invoice unknown)."""
    return {name: None for name in PUBLIC_FIELDS}


# --------------------------------------------------------------------------- #
# JSON Schema given to the model as the tool input schema.
# Hand-written so every key is required and nullable via type arrays. Kept in sync
# with `Extraction` by tests/test_schema.py.
# --------------------------------------------------------------------------- #
_NULLABLE_STR = {"type": ["string", "null"]}
_NULLABLE_NUM = {"type": ["number", "null"]}

EXTRACTION_TOOL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_type": {
            "type": "string",
            "enum": list(DocType.__args__),  # type: ignore[attr-defined]
            "description": "What kind of document this is.",
        },
        "is_invoice": {"type": "boolean", "description": "True only when document_type is invoice."},
        "vendor": {**_NULLABLE_STR, "description": "Name of the seller that issued the invoice."},
        "invoice_number": {**_NULLABLE_STR, "description": "Identifier of this invoice, as printed."},
        "invoice_date": {**_NULLABLE_STR, "description": "Invoice issue date as YYYY-MM-DD."},
        "currency": {**_NULLABLE_STR, "description": "ISO 4217 code such as INR, USD, EUR."},
        "line_items": {
            "type": ["array", "null"],
            "description": "Billed lines in document order.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {**_NULLABLE_NUM, "description": "Units billed, null if not shown."},
                    "amount": {"type": "number", "description": "Line total before tax."},
                },
                "required": ["description", "quantity", "amount"],
            },
        },
        "tax_total": {**_NULLABLE_NUM, "description": "Sum of all tax amounts printed on the invoice."},
        "total": {**_NULLABLE_NUM, "description": "Grand total payable, including tax."},
        "legibility": {"type": "string", "enum": ["good", "fair", "poor"]},
        "confidence": {"type": "number", "description": "0 to 1: confidence that every extracted field is correct."},
        "notes": {**_NULLABLE_STR, "description": "Short remark for a human reviewer, or null."},
    },
    "required": [
        "document_type",
        "is_invoice",
        "vendor",
        "invoice_number",
        "invoice_date",
        "currency",
        "line_items",
        "tax_total",
        "total",
        "legibility",
        "confidence",
        "notes",
    ],
}
