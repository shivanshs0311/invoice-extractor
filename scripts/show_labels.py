#!/usr/bin/env python3
"""Summarise the ground-truth labels in the sample pack. No API calls, no cost.

  python scripts/show_labels.py

For every labelled document it prints the key fields and checks whether the labelled line items
plus tax equal the labelled total, which is the rule our validation relies on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

EIGHT = {"is_invoice", "vendor", "invoice_number", "invoice_date", "currency", "line_items", "tax_total", "total"}


def main() -> int:
    folder = ROOT / "data" / "sample_pack" / "labelled"
    files = sorted(folder.glob("*.json"))
    if not files:
        print(f"No label files found in {folder}")
        return 1

    print(f"{'label':6s} {'inv':5s} {'vendor':26s} {'number':16s} {'date':10s} {'cur':4s} {'items':>5s} {'tax':>10s} {'total':>11s}  items+tax vs total")
    details: list[str] = []
    notes: list[str] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        extra = sorted(set(data) - EIGHT)
        if extra:
            notes.append(f"{path.name}: extra keys {extra}")
        items = data.get("line_items") or []
        tax, total = data.get("tax_total"), data.get("total")
        if data.get("is_invoice") and total is not None and items:
            calc = round(sum(i["amount"] for i in items) + (tax or 0), 2)
            diff = round(calc - total, 2)
            check = "OK" if abs(diff) <= 1.0 else f"MISMATCH calc={calc} diff={diff}"
        else:
            check = "-"
        print(
            f"{path.stem:6s} {str(data.get('is_invoice')):5s} {str(data.get('vendor'))[:26]:26s} {str(data.get('invoice_number'))[:16]:16s} "
            f"{str(data.get('invoice_date')):10s} {str(data.get('currency')):4s} {len(items):>5d} {str(tax):>10s} {str(total):>11s}  {check}"
        )
        if items:
            details.append(f"\n{path.stem}  ({data.get('vendor')}):")
            for it in items:
                details.append(f"    qty={str(it.get('quantity')):6s} amount={str(it.get('amount')):>12s}  {str(it.get('description'))[:60]}")
        if any((i.get("amount") or 0) < 0 for i in items):
            notes.append(f"{path.name}: has a negative (discount) row")
        if any(i.get("quantity") is None for i in items):
            notes.append(f"{path.name}: has rows with quantity null")
        if data.get("is_invoice") and tax == 0:
            notes.append(f"{path.name}: tax_total is 0")
        if data.get("is_invoice") and tax is None:
            notes.append(f"{path.name}: tax_total is null")

    print("\nLINE ITEMS")
    print("\n".join(details))
    print("\nNOTES")
    print("\n".join(notes) if notes else "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
