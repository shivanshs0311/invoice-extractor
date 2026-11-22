"""Plain-language explanations for failures and review flags.

One source of truth for the words a person sees: the API returns these, the frontend shows them, and the
history keeps them. Each failure says what happened, why, and what the person can do about it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Explanation:
    title: str
    why: str
    fix: str


_FAILURES: dict[str, Explanation] = {
    # The file itself
    "file_not_found": Explanation(
        "File not found", "The file was not there when the system tried to read it.", "Upload the file again."
    ),
    "unreadable_file": Explanation(
        "File could not be read", "The system was not allowed to open the file, or it disappeared mid-read.", "Upload it again."
    ),
    "empty_file": Explanation("The file is empty", "It contains 0 bytes, so there is nothing to read.", "Export or download the document again."),
    "file_too_large": Explanation(
        "File is too large",
        "Very large files are slow and expensive to read, so there is a size limit.",
        "Compress the PDF or upload only the invoice pages.",
    ),
    "unsupported_type": Explanation(
        "Not a supported file",
        "The content is not a PDF or an image, even if the file name says so (for example a Word file renamed to .pdf).",
        "Save or export the invoice as PDF, JPG or PNG and upload that.",
    ),
    "corrupt_file": Explanation(
        "The file is damaged",
        "The PDF or image is broken, often from an interrupted download or a bad export.",
        "Download or export the document again from where it came from.",
    ),
    "encrypted_pdf": Explanation(
        "The PDF is password protected", "A locked PDF cannot be opened without its password.", "Remove the password, then upload it again."
    ),
    "no_pages": Explanation("The PDF has no pages", "The file opened but contains no pages.", "Export the document again."),
    "blank_document": Explanation(
        "The page looks blank",
        "There is no text and the page image is empty, so there is nothing to read.",
        "Check that the scan or photo actually captured the document.",
    ),
    # The reading
    "unreadable_document": Explanation(
        "Too unclear to read reliably",
        "The scan is blurry, dark or low resolution. Rather than guess the numbers, the system stopped.",
        "Upload a sharper scan or photo: flat, in good light, with the whole page in view.",
    ),
    "invalid_output": Explanation(
        "The reading came back incomplete",
        "The AI model's answer did not match the required format, even after a retry.",
        "Try again. If it keeps happening, the document may be unusual: enter it by hand.",
    ),
    "internal_error": Explanation(
        "Something went wrong on our side", "An unexpected error happened while processing this file.", "Try again. If it repeats, report the file."
    ),
    # The AI service
    "api_auth": Explanation(
        "The AI service is not set up",
        "The server has no valid API key, so it cannot reach the AI model.",
        "Administrator: put a valid GEMINI_API_KEY in the .env file and restart the server.",
    ),
    "api_quota": Explanation(
        "Daily limit reached",
        "The free plan of the AI service allows a fixed number of requests per day, and today's are used up.",
        "Try again after the daily reset (midnight Pacific time, 13:30 in India), or use a paid key.",
    ),
    "api_rate_limit": Explanation(
        "Too many requests at once", "The AI service asked us to slow down.", "Wait a minute and try again."
    ),
    "api_server_error": Explanation(
        "The AI service is busy",
        "The AI provider is overloaded right now. The system already retried several times.",
        "Wait a few minutes and try again.",
    ),
    "api_timeout": Explanation(
        "The AI service took too long", "No answer arrived in time, even after retries.", "Try again in a minute."
    ),
    "api_connection": Explanation(
        "No connection to the AI service", "The server could not reach the internet or the AI provider.", "Check the internet connection, then try again."
    ),
    "api_bad_request": Explanation(
        "The AI service rejected the request",
        "The request was refused, often because the model name in the settings is wrong.",
        "Administrator: check EXTRACT_MODEL and ESCALATION_MODEL in .env.",
    ),
    "api_truncated": Explanation(
        "The answer was cut off", "The document is so long that the AI's answer hit its length limit.", "Upload only the invoice pages."
    ),
    "api_refusal": Explanation(
        "The AI service declined this document", "The provider's safety filter refused to process it.", "Enter this document by hand."
    ),
    "api_bad_output": Explanation(
        "The AI service sent an unreadable answer", "The reply was not valid JSON.", "Try again."
    ),
}

_UNKNOWN = Explanation(
    "The document could not be processed", "An unexpected problem stopped the extraction.", "Try again, or enter the document by hand."
)

# Why a document was flagged for review. Each check name comes from validate.py.
_REVIEW_REASONS: dict[str, str] = {
    "totals_reconcile": "The line items plus tax do not add up to the total, so one of the numbers was probably misread.",
    "totals_unverifiable": "The total could not be checked, because the line items or the total are missing.",
    "core_fields_present": "A required field (vendor, invoice number, date, total or line items) was not found.",
    "document_type_consistent": "The system was unsure whether this is an invoice.",
    "currency_known": "The currency is missing or is not a recognised currency code.",
    "date_plausible": "The invoice date looks wrong (in the future, or very old).",
    "tax_plausible": "The tax amount looks wrong next to the total.",
    "legibility_good": "The document was hard to read, so some values may be wrong.",
    "confidence_ok": "The AI model was not confident about this reading.",
    "input_quality_ok": "The file has quality problems (low resolution, or some pages were cut off).",
    "non_invoice_fields_null": "This is not an invoice, but invoice fields were found. They were removed.",
}


def explain_failure(code: str | None) -> dict:
    """{code, title, why, fix} for a failed extraction."""
    explanation = _FAILURES.get(code or "", _UNKNOWN)
    return {"code": code, **asdict(explanation)}


def explain_review(reasons: list[str] | None) -> list[str]:
    """One plain sentence per review reason. Failure reasons are left out: the failure explanation covers them."""
    return [_REVIEW_REASONS.get(r, r) for r in (reasons or []) if not r.startswith("extraction_failed:")]


def known_failure_codes() -> set[str]:
    return set(_FAILURES)
