#!/usr/bin/env python3
"""Extractor CLI.

  python extract.py invoice.pdf > out.json            one document, JSON on stdout
  python extract.py invoice.pdf --out out.json        same, written to a file (safest on Windows PowerShell)
  python extract.py data/ --out-dir outputs           every document under data/, one JSON per document

Logs go to stderr so stdout stays pure JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from invoice_extractor.config import ROOT, VALID_MODES, load_settings
from invoice_extractor.data_io import discover_documents
from invoice_extractor.llm import LLMError
from invoice_extractor.pipeline import ExtractionResult, extract_document, extract_many


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract structured invoice data from PDFs and images.")
    p.add_argument("inputs", nargs="+", help="A file, several files, or a directory")
    p.add_argument("--out", help="Single input only: write the JSON to this file instead of stdout")
    p.add_argument("--out-dir", default=str(ROOT / "outputs"), help="Batch mode: folder for <name>.json files (default: outputs/)")
    p.add_argument("--mode", choices=VALID_MODES, help="auto (default), text, vision or hybrid")
    p.add_argument("--model", help="First-pass model (default from .env / EXTRACT_MODEL)")
    p.add_argument("--escalation-model", help="Model used for the one retry (default ESCALATION_MODEL)")
    p.add_argument("--no-escalate", action="store_true", help="Never retry on a stronger model")
    p.add_argument("--with-review", action="store_true", help="Also include needs_review and review_reasons in each JSON (an extension beyond schema.json, which forbids extra keys)")
    p.add_argument("--meta", action="store_true", help="Single input only: include a _meta object (tokens, cost, checks, attempts)")
    p.add_argument("--workers", type=int, default=2, help="Batch mode: parallel documents (default 2, gentle on the free tier)")
    return p


def _dump(obj: dict, to_file: bool) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=not to_file)


def _log_line(name: str, res: ExtractionResult) -> str:
    cost = res.meta.get("cost_usd")
    cost_txt = "n/a" if cost is None else f"${cost:.5f}"
    flag = " NEEDS REVIEW" if res.output.get("needs_review") else ""
    err = f" error={res.meta['error']['code']}" if res.meta.get("error") else ""
    return (
        f"{name}: {res.status}{flag}{err} | {res.meta.get('source_type')} | "
        f"tokens {res.meta['input_tokens']:,}/{res.meta['output_tokens']:,} | {cost_txt} | {res.meta['latency_s']:.1f}s"
    )


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

    paths: list[Path] = []
    for item in args.inputs:
        found = discover_documents(item)
        if not found:
            if Path(item).is_file():
                found = [Path(item)]  # unsupported extension: let the pipeline report it as a bad input
            else:
                print(f"warning: no documents found at {item}", file=sys.stderr)
        paths.extend(found)
    if not paths:
        print("error: nothing to process", file=sys.stderr)
        return 1

    try:
        if len(paths) == 1 and not Path(args.inputs[0]).is_dir():
            res = extract_document(paths[0], settings)
            payload = res.public_json(with_review=args.with_review)
            if args.meta:
                payload = {**payload, "_meta": res.meta}
            text = _dump(payload, to_file=bool(args.out))
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(text + "\n", encoding="utf-8")
            else:
                print(text)
            print(_log_line(paths[0].name, res), file=sys.stderr)
            return 2 if res.status == "failed" else 0

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stems = [p.stem for p in paths]
        names = [p.name if stems.count(p.stem) > 1 else p.stem for p in paths]  # avoid stem collisions

        def progress(i: int, path: Path, res: ExtractionResult) -> None:
            print(f"[done] {_log_line(path.name, res)}", file=sys.stderr)

        results = extract_many(paths, settings, workers=args.workers, progress=progress)
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    log = []
    for path, name, res in zip(paths, names, results):
        (out_dir / f"{name}.json").write_text(
            _dump(res.public_json(with_review=args.with_review), to_file=True) + "\n", encoding="utf-8"
        )
        log.append(
            {
                "file": path.name,
                "status": res.status,
                "needs_review": res.output.get("needs_review"),
                "review_reasons": res.output.get("review_reasons"),
                "source_type": res.meta.get("source_type"),
                "model": res.meta.get("model"),
                "final_mode": res.meta.get("final_mode"),
                "attempts": len(res.meta.get("attempts", [])),
                "input_tokens": res.meta.get("input_tokens"),
                "output_tokens": res.meta.get("output_tokens"),
                "cost_usd": res.meta.get("cost_usd"),
                "latency_s": res.meta.get("latency_s"),
                "error": res.meta.get("error"),
            }
        )
    (out_dir / "_run_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    n = len(results)
    failed = sum(r.status == "failed" for r in results)
    review = sum(r.status == "needs_review" for r in results)
    costs = [r.meta["cost_usd"] for r in results]
    spend = "n/a" if any(c is None for c in costs) else f"${sum(costs):.4f}"
    print(
        f"\nWrote {n} files to {out_dir} | ok={n - failed - review} needs_review={review} failed={failed} | total cost {spend}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
