#!/usr/bin/env python3
"""Run this before you submit:  python scripts/preflight.py

Checks the things reviewers will check first: dependencies and .env.example match the code, no leftover
placeholders in the report, no secrets in the repo or its git history, one output JSON per document, outputs
that validate against schema.json, and that the eval results block was generated from a real run.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from invoice_extractor.data_io import discover_documents  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", "data"}
KEY_PATTERN = r"AIza[0-9A-Za-z_\-]{30,}|AQ\.[A-Za-z0-9_\-]{30,}|(?:GEMINI|GOOGLE)_API_KEY\s*=\s*[A-Za-z0-9_.\-]{12,}"
SECRET = re.compile(KEY_PATTERN)
GIT_KEY_PATTERN = "AIza[0-9A-Za-z_-]{30,}|AQ[.][A-Za-z0-9_-]{30,}|(GEMINI|GOOGLE)_API_KEY[ ]*=[ ]*[A-Za-z0-9_.-]{12,}"  # POSIX form for git -G

results: list[tuple[str, str, str]] = []  # (level, name, detail)


def record(level: str, name: str, detail: str = "") -> None:
    results.append((level, name, detail))


def text_files():
    for p in ROOT.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.name in {".env", ".env.example"} or p.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png", ".pyc", ".zip"}:
            continue
        yield p


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main() -> int:
    # --- fresh-clone basics ----------------------------------------------------------------------------
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8") if (ROOT / "requirements.txt").exists() else ""
    record("ok" if "google-genai" in reqs else "FAIL", "requirements.txt lists google-genai")
    example = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
    key_line = re.search(r"^GEMINI_API_KEY=(.*)$", example, re.M)
    if not key_line:
        record("FAIL", ".env.example has a GEMINI_API_KEY= line")
    else:
        record("FAIL" if key_line.group(1).strip() else "ok", ".env.example has an empty GEMINI_API_KEY=")
    for name in ("README.md", "REPORT.md", "schema.json", "pricing.json", "extract.py", "eval.py"):
        record("ok" if (ROOT / name).exists() else "FAIL", f"{name} exists")

    # --- report ----------------------------------------------------------------------------------------
    report = ROOT / "REPORT.md"
    if report.exists():
        body = report.read_text(encoding="utf-8")
        left = body.count("<<FILL")
        record("FAIL" if left else "ok", "no <<FILL placeholders left in REPORT.md", f"{left} left" if left else "")
        has_results = "| Field | Correct | Accuracy |" in body
        record("ok" if has_results else "FAIL", "REPORT.md contains generated eval results", "" if has_results else "run: python eval.py --write-report")

    # --- secrets ---------------------------------------------------------------------------------------
    leaks = []
    for p in text_files():
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET.search(content):
            leaks.append(str(p.relative_to(ROOT)))
    record("FAIL" if leaks else "ok", "no API keys in repo files", ", ".join(leaks))

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
    record("ok" if re.search(r"^\.env$", gitignore, re.M) else "FAIL", ".env is git-ignored")
    try:
        tracked = git("ls-files", ".env", "data").split()
        tracked = [t for t in tracked if t != "data/README.md"]
        record("FAIL" if tracked else "ok", ".env and data/ are not tracked by git", ", ".join(tracked))
        history = git("log", "--all", "--format=%h", "-G", GIT_KEY_PATTERN).split()
        record("FAIL" if history else "ok", "no API key was ever committed (git history)", "commits: " + ", ".join(history) if history else "")
    except (OSError, subprocess.CalledProcessError):
        record("warn", "git not available or not a repo yet", "re-run after git init and the first commit")

    # --- outputs ---------------------------------------------------------------------------------------
    pack = ROOT / "data" / "sample_pack"
    docs = discover_documents(pack) if pack.exists() else []
    outs = sorted(p for p in (ROOT / "outputs").glob("*.json") if not p.name.startswith("_"))
    if not docs:
        record("warn", "data/sample_pack not found, cannot compare output count", "put the pack there and re-run")
    else:
        record("ok" if len(outs) == len(docs) else "FAIL", f"outputs/ has one JSON per document ({len(outs)} vs {len(docs)})")
        pack_schema = pack / "schema.json"
        if pack_schema.exists():
            same = json.loads(pack_schema.read_text(encoding="utf-8")) == json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
            record("ok" if same else "FAIL", "schema.json is identical to the one in the sample pack")
    if outs:
        try:
            from jsonschema import Draft202012Validator

            validator = Draft202012Validator(json.loads((ROOT / "schema.json").read_text(encoding="utf-8")))
        except ImportError:
            validator = None
            record("warn", "jsonschema not installed, cannot validate against schema.json", "pip install -r requirements-dev.txt")
        bad, failed = [], []
        for p in outs:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                bad.append(p.name)
                continue
            if d.get("error"):
                failed.append(p.name)  # deliberately not schema-valid, see README
                continue
            if validator is not None and list(validator.iter_errors(d)):
                bad.append(p.name)
        if validator is not None:
            record("FAIL" if bad else "ok", "every output validates against schema.json", ", ".join(sorted(set(bad))))
        record("FAIL" if failed else "ok", f"{len(failed)} output(s) are failed extractions", ", ".join(failed))
        log = ROOT / "outputs" / "_run_log.json"
        if log.exists():
            flagged = sum(1 for r in json.loads(log.read_text(encoding="utf-8")) if r.get("needs_review"))
            record("ok", f"{flagged} document(s) flagged needs_review (see outputs/_run_log.json)")
        else:
            record("warn", "outputs/_run_log.json is missing", "it holds the review flags, tokens and cost per file")
    else:
        record("FAIL", "outputs/ contains JSON files", "run: python extract.py data/sample_pack --out-dir outputs")

    ran = (ROOT / "reports" / "runs" / "default" / "results.json").exists()
    record("ok" if ran else "FAIL", "reports/runs/default exists (the eval was run)", "" if ran else "run: python eval.py --write-report")

    width = max(len(n) for _, n, _ in results)
    for level, name, detail in results:
        print(f"[{level:4s}] {name.ljust(width)}  {detail}")
    failures = sum(1 for level, _, _ in results if level == "FAIL")
    print(f"\n{failures} failing check(s) on {date.today()}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
