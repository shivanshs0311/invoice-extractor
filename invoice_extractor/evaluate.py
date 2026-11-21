"""Eval harness: run the extractor on labelled documents and score it field by field.

Matching rules live in matching.py and are restated in REPORT.md.
Field accuracy is computed over documents whose label says is_invoice = true (a non-invoice has
nothing to extract, so counting its null fields would inflate every number). `is_invoice` itself and
the doc-level "all fields correct" row use every labelled document.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Optional

from .config import ROOT, Settings
from .data_io import load_labels
from .llm import LLMClient
from .matching import (
    LineItemScore,
    match_bool,
    match_currency,
    match_date,
    match_id,
    match_line_items,
    match_money,
    match_tax,
    match_vendor,
    norm_vendor,
    to_date,
    to_num,
)
from .pipeline import ExtractionResult, extract_many
from .prompts import PROMPT_SHA, PROMPT_VERSION

SCALAR_FIELDS = ["is_invoice", "vendor", "invoice_number", "invoice_date", "currency", "tax_total", "total"]
FIELD_ORDER = ["is_invoice", "vendor", "invoice_number", "invoice_date", "currency", "line_items", "tax_total", "total"]
MATCHERS: dict[str, Callable[[Any, Any], bool]] = {
    "is_invoice": match_bool,
    "vendor": match_vendor,
    "invoice_number": match_id,
    "invoice_date": match_date,
    "currency": match_currency,
    "tax_total": match_tax,
    "total": lambda p, g: match_money(p, g),
}
REPORTS_DIR = ROOT / "reports"
EVAL_START, EVAL_END = "<!-- EVAL:START -->", "<!-- EVAL:END -->"


class EvalSetupError(Exception):
    pass


@dataclass
class DocEval:
    name: str
    gt: dict
    pred: dict
    meta: dict
    fields: dict[str, bool]
    li: LineItemScore
    errors: list[dict] = field(default_factory=list)

    @property
    def gt_is_invoice(self) -> bool:
        return bool(self.gt.get("is_invoice"))

    @property
    def all_correct(self) -> bool:
        return all(self.fields.values())

    @property
    def flagged(self) -> bool:
        return bool(self.pred.get("needs_review", False))

    @property
    def source_type(self) -> str:
        return self.meta.get("source_type") or "unknown"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_document(name: str, pred: dict, gt: dict, meta: Optional[dict] = None) -> DocEval:
    meta = meta or {}
    fields = {f: MATCHERS[f](pred.get(f), gt.get(f)) for f in SCALAR_FIELDS}
    li = match_line_items(pred.get("line_items"), gt.get("line_items"))
    fields["line_items"] = li.strict
    ordered = {f: fields[f] for f in FIELD_ORDER}
    doc = DocEval(name=name, gt=gt, pred=pred, meta=meta, fields=ordered, li=li)
    for f, ok in ordered.items():
        if not ok:
            doc.errors.append(
                {
                    "file": name,
                    "field": f,
                    "expected": _brief(gt.get(f), f),
                    "got": _brief(pred.get(f), f),
                    "hint": guess_cause(f, pred.get(f), gt.get(f), li),
                    "source": doc.source_type,
                    "flagged": doc.flagged,
                }
            )
    return doc


def _brief(value: Any, field_name: str) -> str:
    if field_name == "line_items":
        n = len(value or [])
        return f"{n} item(s)"
    return "null" if value is None else str(value)


def guess_cause(field_name: str, got: Any, expected: Any, li: LineItemScore) -> str:
    """Cheap heuristic starting point for the manual failure analysis. Always verify by eye."""
    if field_name == "is_invoice":
        return "classification: invoice vs non-invoice"
    if field_name == "line_items":
        if li.n_pred < li.n_gt:
            return f"line items: {li.n_gt - li.n_pred} missing"
        if li.n_pred > li.n_gt:
            return f"line items: {li.n_pred - li.n_gt} extra"
        if li.amount_matched == li.n_gt:
            return "line items: amounts right, wording or quantity differs"
        return "line items: wrong amounts"
    if got is None and expected is not None:
        return "missed field (returned null)"
    if got is not None and expected is None:
        return "extra value (label is null)"
    if field_name in ("tax_total", "total"):
        a, b = to_num(got), to_num(expected)
        if a is not None and b not in (None, 0):
            ratio = a / b
            if any(abs(ratio - r) < 0.01 for r in (10, 100, 1000, 0.1, 0.01, 0.001)):
                return "decimal point or digit grouping misread"
            if field_name == "tax_total" and abs(a - b / 2) < 0.02:
                return "only half the tax captured (split CGST/SGST?)"
        return "wrong number (misread digit or wrong row)"
    if field_name == "invoice_date":
        da, db = to_date(got), to_date(expected)
        if isinstance(da, date) and isinstance(db, date) and da.day == db.month and da.month == db.day:
            return "day and month swapped"
        return "wrong date (due date or another date?)"
    if field_name == "vendor":
        sim = SequenceMatcher(None, norm_vendor(got), norm_vendor(expected)).ratio()
        return "vendor name variant (near miss)" if sim >= 0.6 else "wrong party (customer instead of seller?)"
    if field_name == "invoice_number":
        return "wrong identifier (PO or order number?) or misread characters"
    if field_name == "currency":
        return "wrong or missing currency"
    return "other"


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _pct(num: int, den: int) -> Optional[float]:
    return None if den == 0 else 100.0 * num / den


def summarize(docs: list[DocEval]) -> dict:
    invoices = [d for d in docs if d.gt_is_invoice]
    non_invoices = [d for d in docs if not d.gt_is_invoice]

    rows = []
    rows.append(("is_invoice", sum(d.fields["is_invoice"] for d in docs), len(docs)))
    for f in ["vendor", "invoice_number", "invoice_date", "currency"]:
        rows.append((f, sum(d.fields[f] for d in invoices), len(invoices)))
    rows.append(("line_items (strict: every item right)", sum(d.fields["line_items"] for d in invoices), len(invoices)))
    for f in ["tax_total", "total"]:
        rows.append((f, sum(d.fields[f] for d in invoices), len(invoices)))
    accuracy = [{"field": f, "correct": c, "n": n, "pct": _pct(c, n)} for f, c, n in rows]

    def mean(values: list[float]) -> Optional[float]:
        return None if not values else 100.0 * sum(values) / len(values)

    line_items = {
        "item_f1_pct": mean([d.li.f1 for d in invoices]),
        "amount_only_f1_pct": mean([d.li.amount_f1 for d in invoices]),
        "n": len(invoices),
    }
    exact = sum(d.all_correct for d in docs)
    non_inv = {
        "correct": sum(d.fields["is_invoice"] and d.pred.get("vendor") is None and d.pred.get("total") is None for d in non_invoices),
        "n": len(non_invoices),
    }

    by_source: dict[str, list[DocEval]] = {}
    for d in docs:
        by_source.setdefault(d.source_type, []).append(d)
    source_rows = []
    for src, items in sorted(by_source.items()):
        applicable = [(d.fields[f]) for d in items if d.gt_is_invoice for f in FIELD_ORDER] + [
            d.fields["is_invoice"] for d in items if not d.gt_is_invoice
        ]
        source_rows.append(
            {
                "source": src,
                "docs": len(items),
                "all_correct": sum(d.all_correct for d in items),
                "field_acc_pct": _pct(sum(applicable), len(applicable)),
                "avg_cost": _avg([d.meta.get("cost_usd") for d in items]),
            }
        )

    costs = [d.meta.get("cost_usd") for d in docs]
    cost = {
        "avg_cost_usd": _avg(costs),
        "total_cost_usd": None if any(c is None for c in costs) else sum(costs),
        "avg_input_tokens": _avg([d.meta.get("input_tokens", 0) for d in docs]),
        "avg_output_tokens": _avg([d.meta.get("output_tokens", 0) for d in docs]),
        "avg_latency_s": _avg([d.meta.get("latency_s", 0.0) for d in docs]),
        "docs_with_retry": sum(len(d.meta.get("attempts", [])) > 1 for d in docs),
        "docs_failed": sum(d.meta.get("status") == "failed" for d in docs),
        "n": len(docs),
        "unpriced": any(c is None for c in costs),
    }

    has_error = [d for d in docs if not d.all_correct]
    flagged = [d for d in docs if d.flagged]
    tp = sum(1 for d in docs if d.flagged and not d.all_correct)
    total_field_errors = sum(len(d.errors) for d in docs)
    review = {
        "n": len(docs),
        "flagged": len(flagged),
        "docs_with_errors": len(has_error),
        "true_positive": tp,
        "precision_pct": _pct(tp, len(flagged)),
        "recall_pct": _pct(tp, len(has_error)),
        "errors_in_flagged_pct": _pct(sum(len(d.errors) for d in flagged), total_field_errors),
        "total_field_errors": total_field_errors,
    }

    applicable_all = [d.fields[f] for d in invoices for f in FIELD_ORDER] + [d.fields["is_invoice"] for d in non_invoices]
    errors = [e for d in docs for e in d.errors]
    return {
        "overall_field_pct": _pct(sum(applicable_all), len(applicable_all)),
        "accuracy": accuracy,
        "line_items": line_items,
        "doc_level": {"correct": exact, "n": len(docs), "pct": _pct(exact, len(docs))},
        "non_invoice": non_inv,
        "by_source": source_rows,
        "cost": cost,
        "review": review,
        "errors": errors,
    }


def _avg(values: list) -> Optional[float]:
    nums = [v for v in values if v is not None]
    return None if not nums else sum(nums) / len(nums)


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #
def run_eval(
    data_dir: str | Path,
    settings: Settings,
    *,
    labels: Optional[str | Path] = None,
    tag: str = "default",
    workers: int = 4,
    reuse: bool = False,
    limit: Optional[int] = None,
    only: Optional[str] = None,
    client: Optional[LLMClient] = None,
    progress: Optional[Callable[[str], None]] = None,
    reports_dir: Path = REPORTS_DIR,
) -> tuple[list[DocEval], dict]:
    say = progress or (lambda msg: None)
    label_map = load_labels(data_dir, labels)
    if only:
        label_map = {p: g for p, g in label_map.items() if only.lower() in p.name.lower()}
    if limit:
        label_map = dict(list(label_map.items())[:limit])
    if not label_map:
        raise EvalSetupError(
            f"No labelled documents found under {data_dir}.\n"
            "Put the sample pack under data/sample_pack/ (documents plus the ground-truth JSON files), or pass --data-dir and "
            "--labels. A label file is a JSON object in the assignment schema, named like the document "
            "(invoice_01.pdf <-> invoice_01.json) or one combined JSON keyed by file name."
        )

    paths = list(label_map)
    run_dir = reports_dir / "runs" / tag
    pred_dir = run_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    if reuse:
        results = []
        for p in paths:
            f = pred_dir / f"{p.name}.json"
            if not f.exists():
                raise EvalSetupError(f"--reuse needs saved predictions, but {f} is missing. Run once without --reuse.")
            saved = json.loads(f.read_text(encoding="utf-8"))
            results.append(ExtractionResult(output=saved["output"], meta=saved["meta"]))
        say(f"Loaded {len(results)} saved predictions from {pred_dir}")
    else:
        done = 0

        def progress_cb(i: int, path: Path, res: ExtractionResult) -> None:
            nonlocal done
            done += 1
            say(f"  [{done}/{len(paths)}] {path.name}: {res.status}")

        say(f"Running extractor on {len(paths)} labelled document(s), mode={settings.mode}, model={settings.model}")
        results = extract_many(paths, settings, client, workers=workers, progress=progress_cb)
        for p, res in zip(paths, results):
            (pred_dir / f"{p.name}.json").write_text(
                json.dumps({"output": res.output, "meta": res.meta}, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    docs = [score_document(p.name, r.output, label_map[p], r.meta) for p, r in zip(paths, results)]
    info = {
        "tag": tag,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": settings.mode,
        "model": settings.model,
        "escalation_model": settings.escalation_model if settings.escalate else None,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha": PROMPT_SHA,
        "documents": len(docs),
        "data_dir": str(data_dir),
        "reused_predictions": reuse,
        "wall_time_s": round(time.perf_counter() - started, 1),
    }
    return docs, info


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fmt_pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.0f}%"


def _fmt_usd(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"${v:.5f}" if v < 0.1 else f"${v:.3f}"


def _fmt_int(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:,.0f}"


def ascii_table(headers: list[str], rows: list[list[str]], right: Optional[set[int]] = None) -> str:
    right = right or set()
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]

    def line(cells: list[str]) -> str:
        parts = []
        for i, c in enumerate(cells):
            parts.append(str(c).rjust(widths[i]) if i in right else str(c).ljust(widths[i]))
        return "| " + " | ".join(parts) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    return "\n".join([sep, line(headers), sep, *(line(r) for r in rows), sep])


def md_table(headers: list[str], rows: list[list[str]], right: Optional[set[int]] = None) -> str:
    right = right or set()
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---:" if i in right else "---" for i in range(len(headers))) + " |"
    body = ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def _tables(docs: list[DocEval], s: dict, markdown: bool) -> dict[str, str]:
    mark = (lambda ok: "\u2713" if ok else "\u2717") if markdown else (lambda ok: "ok" if ok else "X")
    render = md_table if markdown else ascii_table

    acc_rows = [[a["field"], f"{a['correct']}/{a['n']}", _fmt_pct(a["pct"])] for a in s["accuracy"]]
    li = s["line_items"]
    acc_rows.insert(6, ["line_items (item-level F1, mean)", f"n={li['n']}", _fmt_pct(li["item_f1_pct"])])
    acc_rows.insert(7, ["line_items (amount-only F1, ignores wording)", f"n={li['n']}", _fmt_pct(li["amount_only_f1_pct"])])
    dl = s["doc_level"]
    acc_rows.append(["ALL fields correct (whole document)", f"{dl['correct']}/{dl['n']}", _fmt_pct(dl["pct"])])
    accuracy = render(["Field", "Correct", "Accuracy"], acc_rows, right={1, 2})

    doc_rows = []
    for d in docs:
        def cell(f: str) -> str:
            return mark(d.fields[f]) if (d.gt_is_invoice or f == "is_invoice") else "-"

        tokens = f"{d.meta.get('input_tokens', 0):,}/{d.meta.get('output_tokens', 0):,}"
        doc_rows.append(
            [
                d.name[:34],
                d.source_type,
                d.meta.get("status", "?"),
                "yes" if d.flagged else "no",
                cell("is_invoice"),
                cell("vendor"),
                cell("invoice_number"),
                cell("invoice_date"),
                cell("currency"),
                cell("line_items"),
                cell("tax_total"),
                cell("total"),
                _fmt_usd(d.meta.get("cost_usd")),
                tokens,
                str(len(d.meta.get("attempts", []))),
            ]
        )
    per_doc = render(
        ["Document", "Source", "Status", "Review", "inv?", "vendor", "inv#", "date", "cur", "items", "tax", "total", "Cost", "Tok in/out", "Calls"],
        doc_rows,
        right={12, 13, 14},
    )

    c = s["cost"]
    cost_rows = [
        ["Average cost per document", _fmt_usd(c["avg_cost_usd"])],
        ["Average input tokens per document", _fmt_int(c["avg_input_tokens"])],
        ["Average output tokens per document", _fmt_int(c["avg_output_tokens"])],
        ["Total spend for this run", _fmt_usd(c["total_cost_usd"])],
        ["Documents that needed a retry or escalation", f"{c['docs_with_retry']}/{c['n']}"],
        ["Documents that failed outright", f"{c['docs_failed']}/{c['n']}"],
        ["Average latency per document", f"{c['avg_latency_s']:.1f}s" if c["avg_latency_s"] is not None else "n/a"],
    ]
    if c["unpriced"]:
        cost_rows.append(["WARNING", "a model is missing from pricing.json, cost is understated"])
    cost = render(["Cost metric", "Value"], cost_rows, right={1})

    src_rows = [
        [r["source"], str(r["docs"]), f"{r['all_correct']}/{r['docs']}", _fmt_pct(r["field_acc_pct"]), _fmt_usd(r["avg_cost"])]
        for r in s["by_source"]
    ]
    by_source = render(["Source type", "Docs", "All fields correct", "Field accuracy", "Avg cost"], src_rows, right={1, 2, 3, 4})

    r = s["review"]
    review_rows = [
        ["Documents flagged needs_review", f"{r['flagged']}/{r['n']}"],
        ["Documents with at least one wrong field", f"{r['docs_with_errors']}/{r['n']}"],
        ["Flag precision (flagged docs that really had errors)", _fmt_pct(r["precision_pct"])],
        ["Flag recall (docs with errors that were flagged)", _fmt_pct(r["recall_pct"])],
        ["Share of all wrong fields that sit in flagged docs", _fmt_pct(r["errors_in_flagged_pct"])],
    ]
    review = render(["Review flag check", "Value"], review_rows, right={1})

    err_rows = [[e["file"][:30], e["field"], e["expected"][:34], e["got"][:34], e["hint"], "yes" if e["flagged"] else "no"] for e in s["errors"]]
    errors = render(["Document", "Field", "Expected", "Got", "Auto-hint (verify by eye)", "Flagged"], err_rows) if err_rows else "No errors."
    return {"accuracy": accuracy, "per_doc": per_doc, "cost": cost, "by_source": by_source, "review": review, "errors": errors}


def format_console(docs: list[DocEval], s: dict, info: dict) -> str:
    t = _tables(docs, s, markdown=False)
    header = (
        f"Run '{info['tag']}': {info['documents']} labelled documents | mode={info['mode']} | model={info['model']}"
        f" | escalation={info['escalation_model'] or 'off'} | prompt {info['prompt_version']} ({info['prompt_sha']})"
    )
    return "\n\n".join(
        [
            header,
            "FIELD-LEVEL ACCURACY (field rows use labelled invoices only, is_invoice and the last row use all documents)\n" + t["accuracy"],
            "PER-DOCUMENT RESULTS\n" + t["per_doc"],
            "ACCURACY BY SOURCE TYPE\n" + t["by_source"],
            "COST (tokens come from the API usage field, priced with pricing.json)\n" + t["cost"],
            "REVIEW FLAG CHECK (small sample, read with care)\n" + t["review"],
            "ERRORS\n" + t["errors"],
        ]
    )


def format_markdown(docs: list[DocEval], s: dict, info: dict) -> str:
    t = _tables(docs, s, markdown=True)
    meta_rows = [
        ["Run tag", info["tag"]],
        ["When", info["timestamp"]],
        ["Documents scored", str(info["documents"])],
        ["Mode", info["mode"]],
        ["Model", info["model"]],
        ["Escalation model", info["escalation_model"] or "off"],
        ["Prompt version", f"{info['prompt_version']} (sha {info['prompt_sha']})"],
    ]
    parts = [
        "#### Run",
        md_table(["Setting", "Value"], meta_rows),
        "#### Field-level accuracy",
        "Field rows use the labelled documents that are invoices. `is_invoice` and the last row use every labelled document.",
        t["accuracy"],
        "#### Per-document results",
        t["per_doc"],
        "#### Accuracy by source type",
        t["by_source"],
        "#### Cost per document",
        t["cost"],
        "#### Review flag check",
        t["review"],
        "#### Errors (auto-hints are a starting point for the failure analysis, verify each by eye)",
        t["errors"],
    ]
    return "\n\n".join(parts)


def save_reports(docs: list[DocEval], s: dict, info: dict, reports_dir: Path = REPORTS_DIR) -> Path:
    run_dir = reports_dir / "runs" / info["tag"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.md").write_text(format_markdown(docs, s, info) + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps({"info": info, "summary": s}, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return run_dir


def update_report_file(report_path: Path, markdown: str) -> bool:
    """Replace the block between the EVAL markers in REPORT.md. Returns False if markers are missing."""
    if not report_path.exists():
        return False
    text = report_path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(EVAL_START) + r".*?" + re.escape(EVAL_END), re.S)
    if not pattern.search(text):
        return False
    block = f"{EVAL_START}\n\n{markdown}\n\n{EVAL_END}"
    report_path.write_text(pattern.sub(lambda _m: block, text), encoding="utf-8")
    return True
