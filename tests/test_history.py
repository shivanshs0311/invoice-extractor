from invoice_extractor.history import History
from invoice_extractor.pipeline import ExtractionResult


def result(status="ok", **output):
    meta = {"status": status, "cost_usd": 0.0012, "error": None}
    if status == "failed":
        meta["error"] = {"code": "corrupt_file", "message": "Cannot open PDF", "detail": "Traceback ..."}
        output["error"] = {"code": "corrupt_file", "message": "Cannot open PDF"}
    return ExtractionResult(output=output, meta=meta)


def test_add_list_get_and_file(tmp_path):
    h = History(tmp_path)
    a = h.add("inv.pdf", b"%PDF-1", result(vendor="Acme", total=10.0, currency="INR"))
    b = h.add("bad.pdf", b"junk", result("failed"))
    assert [r["id"] for r in h.list()] == [b, a]  # newest first
    rec = h.get(a)
    assert rec["vendor"] == "Acme" and rec["output"]["total"] == 10.0 and rec["filename"] == "inv.pdf"
    assert h.file_path(a).read_bytes() == b"%PDF-1"
    assert h.get(b)["error_code"] == "corrupt_file"


def test_list_says_whether_a_document_is_an_invoice(tmp_path):
    h = History(tmp_path)
    h.add("inv.pdf", b"%PDF", result(is_invoice=True, vendor="Acme"))
    h.add("statement.pdf", b"%PDF", result(is_invoice=False))
    h.add("bad.pdf", b"junk", result("failed", is_invoice=None))
    assert [r["is_invoice"] for r in h.list()] == [None, False, True]


def test_stack_traces_are_not_stored(tmp_path):
    h = History(tmp_path)
    rec = h.get(h.add("bad.pdf", b"junk", result("failed")))
    assert "detail" not in rec["meta"]["error"]


def test_history_survives_a_restart_and_delete_removes_the_file(tmp_path):
    record_id = History(tmp_path).add("inv.pdf", b"%PDF-1", result(vendor="Acme"))
    h = History(tmp_path)  # a new instance, as after a server restart
    path = h.file_path(record_id)
    assert h.get(record_id)["vendor"] == "Acme"
    assert h.delete(record_id) is True and h.get(record_id) is None and not path.exists()
    assert h.delete(record_id) is False
