#!/usr/bin/env python3
"""Run the eval under several configurations and print one comparison table.

  python scripts/ablation.py

Use the result for the "approach" part of REPORT.md: which input representation and which model
actually earns its cost. Roughly 5 runs x 10 documents, a few cents in total with the default models.

  python scripts/ablation.py --skip hybrid-strong     leave out the strong-model row (the free tier allows only
                                                      a few strong-model requests per day)
  python scripts/ablation.py --reuse --skip hybrid-strong   rebuild the table from saved predictions, no API calls
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from invoice_extractor.config import ROOT, load_settings
from invoice_extractor.evaluate import (
    EvalSetupError,
    _fmt_pct,
    _fmt_usd,
    md_table,
    run_eval,
    save_reports,
    summarize,
)
from invoice_extractor.llm import LLMError


def configs(base):
    return [
        ("cascade: text/vision first, strong model on failure (default)", "cascade", dict(mode="auto", escalate=True)),
        ("text layer only, cheap model", "text-only", dict(mode="text", escalate=False)),
        ("page images only, cheap model", "vision-only", dict(mode="vision", escalate=False)),
        ("text + images, cheap model", "hybrid-cheap", dict(mode="hybrid", escalate=False)),
        ("text + images, strong model only", "hybrid-strong", dict(mode="hybrid", escalate=False, model=base.escalation_model)),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "sample_pack"))
    ap.add_argument("--labels")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--reuse", action="store_true", help="Re-score saved ablation predictions without API calls")
    ap.add_argument("--skip", nargs="*", default=[], help="Configuration tags to leave out, e.g. hybrid-strong")
    args = ap.parse_args()

    base = load_settings()
    rows = []
    for label, tag, overrides in configs(base):
        if tag in args.skip:
            rows.append([label, "not run", "-", "-", "-", "-"])
            continue
        settings = base.with_overrides(**overrides)
        print(f"\n== {label}", file=sys.stderr)
        try:
            docs, info = run_eval(
                args.data_dir,
                settings,
                labels=args.labels,
                tag=f"ablation-{tag}",
                workers=args.workers,
                reuse=args.reuse,
                progress=lambda m: print(m, file=sys.stderr),
            )
        except (EvalSetupError, LLMError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        s = summarize(docs)
        save_reports(docs, s, info)
        rows.append(
            [
                label,
                f"{s['doc_level']['correct']}/{s['doc_level']['n']}",
                _fmt_pct(s["overall_field_pct"]),
                _fmt_usd(s["cost"]["avg_cost_usd"]),
                _fmt_usd(s["cost"]["total_cost_usd"]),
                f"{s['cost']['docs_with_retry']}/{s['cost']['n']}",
            ]
        )

    table = md_table(
        ["Configuration", "Docs fully correct", "Field accuracy", "Avg cost / doc", "Run cost", "Docs retried"],
        rows,
        right={1, 2, 3, 4, 5},
    )
    print("\n" + table)
    out = ROOT / "reports" / "ablation.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(table + "\n", encoding="utf-8")
    print(f"\nSaved {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
