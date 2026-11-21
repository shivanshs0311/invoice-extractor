#!/usr/bin/env python3
"""Live check of prompt + client + schema against the real API (uses a little free quota).

  python scripts/try_llm.py                       text route and vision route on a fake invoice
  python scripts/try_llm.py --model gemini-3.1-flash-lite
  python scripts/try_llm.py --file data/sample_pack/labelled/L01.pdf --mode vision
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from invoice_extractor.config import load_settings
from invoice_extractor.ingest import load_document
from invoice_extractor.llm import LLMError, make_client
from invoice_extractor.prompts import SYSTEM_PROMPT, build_content
from invoice_extractor.schema import EXTRACTION_TOOL_SCHEMA, Extraction


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--file", help="Use this document instead of the generated fake invoice")
    ap.add_argument("--mode", choices=["text", "vision", "both"], default="both")
    args = ap.parse_args()

    settings = load_settings()
    model = args.model or settings.model
    if args.file:
        path = Path(args.file)
    else:
        from factories import digital_pdf

        path = digital_pdf(Path(tempfile.mkdtemp()) / "fake_invoice.pdf")
    doc = load_document(path, settings)
    print(f"document: {path.name} ({doc.source_type}, {doc.page_count} page(s)), model: {model}")

    try:
        client = make_client(settings)
    except LLMError as exc:
        print("error:", exc)
        return 1
    modes = ["text", "vision"] if args.mode == "both" else [args.mode]
    for mode in modes:
        if mode == "text" and not doc.has_text:
            print("\n--- text: skipped (this document has no text layer)")
            continue
        print(f"\n--- {mode} route")
        try:
            result = client.extract(model=model, system=SYSTEM_PROMPT, content=build_content(doc, mode),
                                    tool_schema=EXTRACTION_TOOL_SCHEMA, max_tokens=settings.max_output_tokens)
        except LLMError as exc:
            print(f"FAILED ({exc.kind}, retryable={exc.retryable}): {exc}")
            continue
        print(f"{result.latency_s:.1f}s, tokens in={result.usage.input_tokens} out={result.usage.output_tokens}, finish={result.stop_reason}")
        print(json.dumps(result.data, indent=2)[:1800])
        try:
            Extraction.model_validate(result.data)
            print("schema check: OK")
        except Exception as exc:
            print("schema check: FAILED:", str(exc)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
