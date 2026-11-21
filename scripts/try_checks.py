#!/usr/bin/env python3
"""See the validation checks work on a real extraction, and watch them catch deliberate mistakes.

  python scripts/try_checks.py --file data/sample_pack/labelled/L04.pdf     one live call (free quota)
  python scripts/try_checks.py --offline                                    no API call, canned answer
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from invoice_extractor.config import load_settings
from invoice_extractor.ingest import load_document
from invoice_extractor.llm import LLMError, make_client
from invoice_extractor.prompts import SYSTEM_PROMPT, build_content
from invoice_extractor.schema import EXTRACTION_TOOL_SCHEMA
from invoice_extractor.validate import normalise_tax, parse_extraction, run_checks


def show(title, ext, settings, warnings=None):
    report = run_checks(ext, settings, warnings or [])
    print(f"\n=== {title}")
    for check in report.checks:
        mark = "ok  " if check.ok else ("FAIL" if check.severity == "error" else "warn")
        print(f"  [{mark}] {check.name:26s} {check.detail}")
    verdict = "passes (no retry needed)" if report.passed else "FAILS: this would trigger a retry on the stronger model"
    print(f"  -> {verdict}; review reasons: {report.review_reasons or 'none'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    settings = load_settings()

    warnings: list[str] = []
    if args.offline:
        from fakes import invoice_payload

        raw = invoice_payload(tax_total=None, total=17750.0)
    else:
        if not args.file:
            print("Give --file PATH, or use --offline")
            return 1
        doc = load_document(args.file, settings)
        warnings = doc.warnings
        mode = "text" if doc.has_text and doc.text_ok else "vision"
        try:
            result = make_client(settings).extract(model=settings.model, system=SYSTEM_PROMPT, content=build_content(doc, mode),
                                                   tool_schema=EXTRACTION_TOOL_SCHEMA, max_tokens=settings.max_output_tokens)
        except LLMError as exc:
            print(f"FAILED ({exc.kind}): {exc}")
            return 1
        raw = result.data
        print(f"read {Path(args.file).name} via the {mode} route")

    ext, problems = parse_extraction(raw)
    if ext is None:
        print("schema problems:", problems)
        return 1
    ext, notes = normalise_tax(ext, settings.total_tolerance)
    if notes:
        print("normalised:", notes[0])
    show("the real extraction", ext, settings, warnings)

    if ext.line_items and len(ext.line_items) > 1 and ext.total is not None:
        show("what if the model MISSED the last row?", ext.model_copy(update={"line_items": ext.line_items[:-1]}), settings, warnings)
        show("what if the model MISREAD the total by +1000?", ext.model_copy(update={"total": ext.total + 1000}), settings, warnings)
        show("what if the model forgot the invoice number?", ext.model_copy(update={"invoice_number": None}), settings, warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
