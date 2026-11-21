#!/usr/bin/env python3
"""Look at every document in the sample pack. No API calls, no cost.

  python scripts/inspect_pack.py
  python scripts/inspect_pack.py --dump reports/pack_preview     (also saves the page images the model would see)
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoice_extractor.config import ROOT, load_settings
from invoice_extractor.ingest import IngestError, load_document

EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=str(ROOT / "data" / "sample_pack"))
    ap.add_argument("--dump", help="Folder to save rendered page images into")
    args = ap.parse_args()

    pack = Path(args.pack)
    files = sorted(p for p in pack.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)
    if not files:
        print(f"No documents found under {pack}. Unzip the sample pack there first.")
        return 1

    settings = load_settings()
    counts: dict[str, int] = {}
    print(f"{'file':28s} {'type':12s} {'pages':>5s} {'text chars':>10s}  notes")
    for path in files:
        label = f"{path.parent.name}/{path.name}"
        try:
            doc = load_document(path, settings)
        except IngestError as exc:
            counts[f"error:{exc.code}"] = counts.get(f"error:{exc.code}", 0) + 1
            print(f"{label:28s} {'ERROR':12s} {'':>5s} {'':>10s}  {exc.code}: {exc.message}")
            continue
        counts[doc.source_type] = counts.get(doc.source_type, 0) + 1
        notes = ", ".join(doc.warnings)
        print(f"{label:28s} {doc.source_type:12s} {doc.page_count:>5d} {len(doc.text):>10d}  {notes}")
        if args.dump:
            out = Path(args.dump)
            out.mkdir(parents=True, exist_ok=True)
            for image in doc.images():
                (out / f"{path.stem}_p{image.index + 1}.jpg").write_bytes(base64.b64decode(image.data_b64))

    print("\nSummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
