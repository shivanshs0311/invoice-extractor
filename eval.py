#!/usr/bin/env python3
"""One command: run the extractor on the labelled documents and print the results table.

  python eval.py                       default run (cascade: cheap model first, stronger model on failure)
  python eval.py --write-report        also refresh the results block inside REPORT.md
  python eval.py --reuse               re-score saved predictions without calling the API (after changing matching rules)
  python eval.py --mode text --no-escalate --tag text-only      an ablation run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from invoice_extractor.config import ROOT, VALID_MODES, load_settings
from invoice_extractor.evaluate import (
    EvalSetupError,
    format_console,
    format_markdown,
    run_eval,
    save_reports,
    summarize,
    update_report_file,
)
from invoice_extractor.llm import LLMError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate the extractor against labelled documents.")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "sample_pack"), help="Folder with the sample pack (default: data/sample_pack)")
    p.add_argument("--labels", help="Labels file or folder if they are not under --data-dir")
    p.add_argument("--mode", choices=VALID_MODES)
    p.add_argument("--model")
    p.add_argument("--escalation-model")
    p.add_argument("--no-escalate", action="store_true")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--tag", default="default", help="Name of this run; outputs go to reports/runs/<tag>/")
    p.add_argument("--reuse", action="store_true", help="Score saved predictions instead of calling the API")
    p.add_argument("--limit", type=int, help="Only the first N labelled documents (cheap smoke test)")
    p.add_argument("--only", help="Only documents whose file name contains this text")
    p.add_argument("--write-report", action="store_true", help="Update the results block in REPORT.md")
    p.add_argument("--report-path", default=str(ROOT / "REPORT.md"))
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    settings = load_settings(
        mode=args.mode,
        model=args.model,
        escalation_model=args.escalation_model,
        escalate=False if args.no_escalate else None,
    )
    try:
        docs, info = run_eval(
            args.data_dir,
            settings,
            labels=args.labels,
            tag=args.tag,
            workers=args.workers,
            reuse=args.reuse,
            limit=args.limit,
            only=args.only,
            progress=lambda msg: print(msg, file=sys.stderr),
        )
    except (EvalSetupError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = summarize(docs)
    print(format_console(docs, summary, info))
    run_dir = save_reports(docs, summary, info)
    print(f"\nSaved: {run_dir / 'results.md'} and {run_dir / 'results.json'}", file=sys.stderr)

    if args.write_report:
        ok = update_report_file(Path(args.report_path), format_markdown(docs, summary, info))
        msg = "REPORT.md results block updated." if ok else "REPORT.md has no EVAL markers, nothing updated."
        print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
