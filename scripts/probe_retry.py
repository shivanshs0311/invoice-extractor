#!/usr/bin/env python3
"""Find out why the stronger model fails. Tries each model on ONE document and prints the real error.

  python scripts/probe_retry.py
  python scripts/probe_retry.py --file data/sample_pack/labelled/L01.pdf --timeout 150
  python scripts/probe_retry.py --specs gemini-3.5-flash:low gemini-3.6-flash

A spec is MODEL or MODEL:LEVEL, where LEVEL is default, minimal, low, medium or high (thinking level).
Uses a little free quota (one call per spec). Ctrl+C stops early and still prints the table.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from invoice_extractor.config import load_settings
from invoice_extractor.ingest import IngestError, load_document
from invoice_extractor.llm import GeminiClient, LLMError, to_gemini_schema
from invoice_extractor.prompts import SYSTEM_PROMPT, build_content
from invoice_extractor.schema import EXTRACTION_TOOL_SCHEMA, Extraction

DEFAULT_SPECS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash:low",
    "gemini-3.5-flash:minimal",
    "gemini-3.6-flash",
    "gemini-3.6-flash:low",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
]


def find_default_file() -> Path:
    for pattern in ("data/sample_pack/labelled/L04.*", "data/sample_pack/**/L04.*"):
        hits = sorted(p for p in ROOT.glob(pattern) if p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"))
        if hits:
            return hits[0]
    raise SystemExit("Could not find L04. Pass --file with a path to a document.")


def call_once(gc, spec: str, content: list, max_tokens: int, out: dict) -> None:
    """Runs in a worker thread so the main thread can print a heartbeat while we wait."""
    types = gc._types
    model, _, level = spec.partition(":")
    cfg = dict(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=types.Schema.model_validate(to_gemini_schema(EXTRACTION_TOOL_SCHEMA)),
        max_output_tokens=max_tokens,
    )
    if level and level != "default":
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level=types.ThinkingLevel[level.upper()])
    started = time.perf_counter()
    try:
        resp = gc._client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[gc._part(p) for p in content])],
            config=types.GenerateContentConfig(**cfg),
        )
        out["seconds"] = time.perf_counter() - started
        meta = resp.usage_metadata
        out["in"] = (getattr(meta, "prompt_token_count", 0) or 0) if meta else 0
        out["answer"] = (getattr(meta, "candidates_token_count", 0) or 0) if meta else 0
        out["thoughts"] = (getattr(meta, "thoughts_token_count", 0) or 0) if meta else 0
        cands = resp.candidates or []
        fin = getattr(cands[0], "finish_reason", None) if cands else None
        out["finish"] = getattr(fin, "name", str(fin)) if fin else None
        text = (resp.text or "").strip() if cands else ""
        if not text:
            out["status"] = "EMPTY"
            out["detail"] = f"no text in the reply (finish={out['finish']})"
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            out["status"] = "BAD_JSON"
            out["detail"] = f"{exc} | tail: {text[-120:]!r}"
            return
        try:
            Extraction.model_validate(data)
            out["schema"] = "OK"
        except Exception as exc:
            out["schema"] = "FAILED: " + str(exc).replace("\n", " ")[:200]
        out["items"] = len(data.get("line_items") or [])
        out["total"] = data.get("total")
        out["status"] = "OK" if out["finish"] in (None, "STOP") else out["finish"]
    except Exception as exc:  # we want the raw truth here, whatever it is
        out["seconds"] = time.perf_counter() - started
        out["status"] = "ERROR"
        code = getattr(exc, "code", None)
        out["detail"] = f"{type(exc).__name__}" + (f" code={code}" if code else "") + f": {str(exc)[:500]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="document to use (default: L04, the 24-row invoice)")
    ap.add_argument("--mode", choices=["auto", "text", "vision"], default="auto")
    ap.add_argument("--timeout", type=float, default=90.0, help="seconds to wait per call")
    ap.add_argument("--specs", nargs="*", default=DEFAULT_SPECS)
    args = ap.parse_args()

    settings = dataclasses.replace(load_settings(), timeout_s=args.timeout)
    path = Path(args.file) if args.file else find_default_file()
    try:
        doc = load_document(path, settings)
    except IngestError as exc:
        print("could not load the document:", exc)
        return 1
    mode = args.mode if args.mode != "auto" else ("text" if doc.has_text else "vision")
    content = build_content(doc, mode)
    print(f"document: {path.name} ({doc.source_type}, {doc.page_count} page(s)), route: {mode}, timeout: {args.timeout:.0f}s per call")
    print(f"max_output_tokens: {settings.max_output_tokens}")

    try:
        gc = GeminiClient(settings)
    except LLMError as exc:
        print("error:", exc)
        return 1

    rows = []
    try:
        for n, spec in enumerate(args.specs, 1):
            print(f"\n[{n}/{len(args.specs)}] {spec}", flush=True)
            out: dict = {"spec": spec}
            worker = threading.Thread(target=call_once, args=(gc, spec, content, settings.max_output_tokens, out), daemon=True)
            started = time.perf_counter()
            worker.start()
            waited = 0
            while worker.is_alive() and time.perf_counter() - started < args.timeout + 20:
                worker.join(10)
                if worker.is_alive():
                    waited += 10
                    print(f"   ...waiting {waited}s", flush=True)
            if worker.is_alive():
                out.setdefault("status", "HUNG")
                out.setdefault("detail", "no answer and no error after the timeout plus 20s")
                out.setdefault("seconds", time.perf_counter() - started)
            rows.append(out)
            if out["status"] in ("OK",) or "items" in out:
                print(f"   {out['status']} in {out['seconds']:.1f}s | tokens in={out['in']} answer={out['answer']} thoughts={out['thoughts']} | "
                      f"finish={out['finish']} | items={out['items']} total={out['total']} | schema={out['schema']}")
            else:
                print(f"   {out['status']} after {out['seconds']:.1f}s")
                print(f"   {out.get('detail', '')}")
    except KeyboardInterrupt:
        print("\nstopped early with Ctrl+C")

    print("\n=== summary ===")
    print(f"{'spec':<28}{'status':<10}{'seconds':>8}{'thoughts':>10}{'out':>7}  items  note")
    for r in rows:
        note = "" if r["status"] == "OK" else (r.get("detail") or "")[:70]
        print(f"{r['spec']:<28}{r['status']:<10}{r.get('seconds', 0):>8.1f}{r.get('thoughts', 0):>10}{r.get('answer', 0):>7}  "
              f"{str(r.get('items', '-')):<5}  {note}")
    print("\nPaste this whole output back to me.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
