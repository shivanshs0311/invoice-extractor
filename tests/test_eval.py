import json

import pytest

from factories import digital_pdf
from fakes import FakeClient, good_payload, invoice_payload
from invoice_extractor.config import Settings
from invoice_extractor.data_io import discover_documents, load_labels
from invoice_extractor.evaluate import (
    EvalSetupError, format_console, format_markdown, run_eval, save_reports, score_document, summarize, update_report_file,
)

S = Settings(api_backoff_s=0.0)
INVOICE_LABEL = {
    "is_invoice": True, "vendor": "Sharma Office Supplies Pvt Ltd", "invoice_number": "SOS/2026/0412", "invoice_date": "2026-03-14",
    "currency": "INR",
    "line_items": [{"description": "A4 paper, 500 sheets", "quantity": 10, "amount": 3200.0},
                   {"description": "Laser printer toner", "quantity": 3, "amount": 14550.0}],
    "tax_total": 0.0, "total": 17750.0,
}
NON_INVOICE_LABEL = {k: None for k in INVOICE_LABEL} | {"is_invoice": False}
NON_INVOICE_PAYLOAD = invoice_payload(document_type="bank_statement", is_invoice=False, vendor=None, invoice_number=None,
                                      invoice_date=None, currency=None, line_items=None, tax_total=None, total=None)


def make_pack(root):
    """Three labelled documents A, B, C (sorted order). A: invoice, B: non-invoice, C: invoice."""
    root.mkdir()
    for name, label in (("A", INVOICE_LABEL), ("B", NON_INVOICE_LABEL), ("C", INVOICE_LABEL)):
        digital_pdf(root / f"{name}.pdf")
        (root / f"{name}.json").write_text(json.dumps(label), encoding="utf-8")
    return root


def handler(n, model, content):
    """Call 1 reads A correctly, call 2 says B is not an invoice, then C is read wrongly every time (retry included)."""
    if n == 1:
        return good_payload()
    if n == 2:
        return NON_INVOICE_PAYLOAD
    return good_payload(total=1.0)


@pytest.fixture()
def eval_run(tmp_path):
    pack = make_pack(tmp_path / "pack")
    client = FakeClient(handler)
    docs, info = run_eval(pack, S, client=client, reports_dir=tmp_path / "reports", workers=1)
    return docs, info, tmp_path, pack, client


def test_eval_scores_and_summary(eval_run):
    docs, info, *_ = eval_run
    assert [d.name for d in docs] == ["A.pdf", "B.pdf", "C.pdf"]
    s = summarize(docs)
    assert s["doc_level"] == {"correct": 2, "n": 3, "pct": pytest.approx(66.67, abs=0.01)}
    assert s["non_invoice"] == {"correct": 1, "n": 1}
    acc = {a["field"]: a for a in s["accuracy"]}
    assert acc["is_invoice"]["pct"] == 100.0
    assert acc["total"]["n"] == 2 and acc["total"]["correct"] == 1  # field rows only count labelled invoices


def test_review_flag_analysis_catches_the_error(eval_run):
    docs, *_ = eval_run
    r = summarize(docs)["review"]
    assert r["flagged"] == 1 and r["docs_with_errors"] == 1 and r["true_positive"] == 1
    assert r["precision_pct"] == 100.0 and r["recall_pct"] == 100.0


def test_cost_summary_counts_retries(eval_run):
    docs, *_ = eval_run
    c = summarize(docs)["cost"]
    assert c["n"] == 3 and c["docs_with_retry"] == 1 and c["docs_failed"] == 0
    assert c["avg_input_tokens"] > 0 and c["avg_cost_usd"] > 0 and not c["unpriced"]


def test_reports_are_rendered_and_saved(eval_run):
    docs, info, tmp_path, *_ = eval_run
    s = summarize(docs)
    console = format_console(docs, s, info)
    assert "FIELD-LEVEL ACCURACY" in console and "A.pdf" in console
    assert "\u2713" not in console and "\u2717" not in console  # console output stays ASCII-safe for Windows terminals
    md = format_markdown(docs, s, info)
    assert "| Field | Correct | Accuracy |" in md and "\u2713" in md
    run_dir = save_reports(docs, s, info, tmp_path / "reports")
    assert (run_dir / "results.md").exists() and json.loads((run_dir / "results.json").read_text())["info"]["tag"] == "default"
    assert (tmp_path / "reports" / "runs" / "default" / "predictions" / "A.pdf.json").exists()


def test_reuse_rescoring_makes_no_api_calls(eval_run):
    _, _, tmp_path, pack, _ = eval_run
    never = FakeClient(lambda n, m, c: pytest.fail("no API call expected with --reuse"))
    docs, info = run_eval(pack, S, client=never, reports_dir=tmp_path / "reports", reuse=True)
    assert len(docs) == 3 and info["reused_predictions"] is True and never.calls == []


def test_reuse_without_saved_predictions_explains(tmp_path):
    pack = make_pack(tmp_path / "pack")
    with pytest.raises(EvalSetupError):
        run_eval(pack, S, client=FakeClient(lambda *a: {}), reports_dir=tmp_path / "reports", reuse=True)


def test_update_report_markers(tmp_path):
    report = tmp_path / "REPORT.md"
    report.write_text("intro\n<!-- EVAL:START -->\nold\n<!-- EVAL:END -->\noutro\n", encoding="utf-8")
    assert update_report_file(report, "NEW TABLE")
    text = report.read_text(encoding="utf-8")
    assert "NEW TABLE" in text and "old" not in text and text.startswith("intro") and text.rstrip().endswith("outro")
    assert update_report_file(report, "SECOND")  # idempotent
    assert text.count("EVAL:START") == 1
    report.write_text("no markers", encoding="utf-8")
    assert update_report_file(report, "x") is False


def test_score_document_hints():
    gt = {"is_invoice": True, "vendor": "Acme Ltd", "invoice_number": "A-1", "invoice_date": "2026-03-04", "currency": "INR",
          "line_items": [{"description": "x", "quantity": 1, "amount": 100.0}], "tax_total": 18.0, "total": 118.0}
    pred = {**gt, "invoice_date": "2026-04-03", "total": 11800.0, "tax_total": 9.0, "vendor": "Beta Corp", "line_items": []}
    doc = score_document("d.pdf", {**pred, "needs_review": False}, gt)
    hints = {e["field"]: e["hint"] for e in doc.errors}
    assert "swapped" in hints["invoice_date"]
    assert "decimal" in hints["total"]
    assert "half" in hints["tax_total"]
    assert "wrong party" in hints["vendor"]
    assert "missing" in hints["line_items"]
    assert not doc.all_correct and doc.flagged is False


def test_failed_documents_count_as_wrong_everywhere():
    gt = {"is_invoice": True, "vendor": "A", "invoice_number": "1", "invoice_date": "2026-01-01", "currency": "USD",
          "line_items": [{"description": "x", "quantity": 1, "amount": 5.0}], "tax_total": None, "total": 5.0}
    failed = {k: None for k in gt} | {"needs_review": True}
    doc = score_document("f.pdf", failed, gt, {"status": "failed", "attempts": []})
    assert doc.fields["is_invoice"] is False and doc.fields["total"] is False and doc.fields["tax_total"] is True  # null == null
    assert doc.flagged


# ---------------------------------------------------------------- label discovery
def _mini(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    digital_pdf(root / "inv_one.pdf")
    digital_pdf(root / "inv_two.pdf")
    return root


def test_labels_per_file_with_gt_suffix(tmp_path):
    root = _mini(tmp_path)
    (root / "inv_one_gt.json").write_text(json.dumps(INVOICE_LABEL))
    (root / "inv_two.pdf.json").write_text(json.dumps(INVOICE_LABEL))
    assert sorted(p.name for p in load_labels(root)) == ["inv_one.pdf", "inv_two.pdf"]


def test_labels_combined_dict_and_list_and_wrapped(tmp_path):
    root = _mini(tmp_path)
    (root / "ground_truth.json").write_text(json.dumps({"inv_one.pdf": INVOICE_LABEL, "inv_two.pdf": {"ground_truth": INVOICE_LABEL}}))
    assert len(load_labels(root)) == 2
    (root / "ground_truth.json").write_text(json.dumps([{"file": "inv_one.pdf", **INVOICE_LABEL}, {"filename": "inv_two", **INVOICE_LABEL}]))
    assert len(load_labels(root)) == 2


def test_labels_in_separate_folder_and_missing(tmp_path):
    root = _mini(tmp_path)
    lab = tmp_path / "elsewhere"
    lab.mkdir()
    (lab / "inv_one.json").write_text(json.dumps(INVOICE_LABEL))
    assert [p.name for p in load_labels(root, lab)] == ["inv_one.pdf"]
    assert load_labels(root) == {}
    with pytest.raises(EvalSetupError) as err:
        run_eval(root, S, client=FakeClient(lambda *a: {}), reports_dir=tmp_path / "reports")
    assert "No labelled documents" in str(err.value)


def test_discovery_skips_outputs_and_reports(tmp_path):
    root = _mini(tmp_path)
    (root / "outputs").mkdir()
    digital_pdf(root / "outputs" / "dup.pdf")
    assert [p.name for p in discover_documents(root)] == ["inv_one.pdf", "inv_two.pdf"]
