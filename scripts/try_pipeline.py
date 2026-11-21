#!/usr/bin/env python3
"""Run the full pipeline on one document and show exactly what happened.

  python scripts/try_pipeline.py data/sample_pack/labelled/L04.pdf     live (free quota)
  python scripts/try_pipeline.py --offline                             no API call
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
from invoice_extractor.llm import LLMError
from invoice_extractor.pipeline import extract_document


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    settings = load_settings()

    client = None
    if args.offline:
        from factories import digital_pdf
        from fakes import FakeClient, good_payload

        path = digital_pdf(Path(tempfile.mkdtemp()) / "fake_invoice.pdf")
        client = FakeClient(lambda n, m, c: good_payload())
    elif args.file:
        path = Path(args.file)
    else:
        print("Give a file path, or use --offline")
        return 1

    try:
        res = extract_document(path, settings, client)
    except LLMError as exc:
        print("configuration error:", exc)
        return 1

    print(json.dumps(res.public_json(with_review=True), indent=2))
    m = res.meta
    print(f"\nstatus: {res.status} | source: {m['source_type']} | final route: {m['final_mode']} with {m['model']}")
    print(f"needs_review: {res.output.get('needs_review')} {res.output.get('review_reasons') or ''}")
    if m.get("normalisations"):
        print("normalised:", m["normalisations"])
    if m.get("notes"):
        print("model note:", m["notes"])
    if m.get("error"):
        print("error:", m["error"]["code"], "-", m["error"]["message"])
    print("\nattempts:")
    for a in m["attempts"]:
        cost = "n/a" if a["cost_usd"] is None else f"${a['cost_usd']:.5f}"
        print(f"  #{a['attempt']} {a['mode']:6s} {a['model']:22s} {a['status']:14s} tokens {a['input_tokens']}/{a['output_tokens']} "
              f"{cost} {a['latency_s']}s api_retries={a['api_retries']} failed={a['failed_checks'] or '-'}")
    total = "n/a" if m["cost_usd"] is None else f"${m['cost_usd']:.5f}"
    print(f"total: tokens {m['input_tokens']}/{m['output_tokens']}, list-price cost {total}, {m['latency_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
