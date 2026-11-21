#!/usr/bin/env python3
"""Compact view of extractor outputs, to check by eye against the PDFs.

  python scripts/show_outputs.py                 the unlabelled documents (outputs/U*.json)
  python scripts/show_outputs.py --prefix L      any other prefix
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="U")
    ap.add_argument("--folder", default=str(ROOT / "outputs"))
    ap.add_argument("--pack", default=str(ROOT / "data" / "sample_pack"))
    args = ap.parse_args()

    files = sorted(p for p in Path(args.folder).glob(f"{args.prefix}*.json") if not p.name.startswith("_"))
    if not files:
        print(f"No outputs starting with {args.prefix} in {args.folder}")
        return 1
    non_invoices = []
    for path in files:
        d = json.loads(path.read_text(encoding="utf-8"))
        doc = next(iter(Path(args.pack).rglob(path.stem + ".*")), None)
        where = f"  ({doc})" if doc and doc.suffix.lower() != ".json" else ""
        print(f"\n=== {path.stem}{where}")
        if not d.get("is_invoice"):
            non_invoices.append(path.stem)
            print("    NOT AN INVOICE" + ("  (error: %s)" % d["error"]["code"] if d.get("error") else ""))
            continue
        items = d.get("line_items") or []
        calc = round(sum(i["amount"] for i in items) + (d.get("tax_total") or 0), 2)
        check = "OK" if d.get("total") is not None and abs(calc - d["total"]) <= 1.0 else f"MISMATCH (calc {calc})"
        print(f"    vendor   : {d.get('vendor')}")
        print(f"    number   : {d.get('invoice_number')}    date: {d.get('invoice_date')}    currency: {d.get('currency')}")
        print(f"    tax_total: {d.get('tax_total')}    total: {d.get('total')}    items+tax vs total: {check}")
        for i in items:
            print(f"      qty={str(i.get('quantity')):6s} amount={str(i['amount']):>12s}  {i['description'][:58]}")
    print(f"\nNot invoices: {non_invoices or 'none'}   ({len(non_invoices)} of {len(files)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
