from factories import digital_pdf, photo_jpg
from invoice_extractor.config import Settings
from invoice_extractor.ingest import load_document
from invoice_extractor.prompts import PROMPT_SHA, PROMPT_VERSION, SYSTEM_PROMPT, build_content

S = Settings()


def texts(parts):
    return "\n".join(p["text"] for p in parts if p["type"] == "text")


def test_text_mode_sends_the_text_layer_and_no_images(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf"), S)
    parts = build_content(doc, "text")
    assert "TEXT LAYER" in texts(parts) and "SOS/2026/0412" in texts(parts)
    assert not any(p["type"] == "image" for p in parts)


def test_vision_mode_sends_page_images_and_no_text_layer(tmp_path):
    doc = load_document(photo_jpg(tmp_path / "p.jpg"), S)
    parts = build_content(doc, "vision")
    assert any(p["type"] == "image" and p["media_type"] == "image/jpeg" for p in parts)
    assert "TEXT LAYER" not in texts(parts)


def test_hybrid_mode_sends_both(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf"), S)
    parts = build_content(doc, "hybrid")
    assert "TEXT LAYER" in texts(parts) and any(p["type"] == "image" for p in parts)


def test_retry_feedback_quotes_the_problem_and_the_previous_answer(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf"), S)
    parts = build_content(doc, "text", feedback="- totals_reconcile: sum is 1 but total is 2", previous={"total": 2})
    joined = texts(parts)
    assert "rejected by automatic checks" in joined and "totals_reconcile" in joined and '"total": 2' in joined
    assert "Do not edit numbers just to make totals add up" in joined


def test_page_count_note_mentions_truncation(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf", pages=3), S.with_overrides(max_pages=1))
    assert "only the first 1 are included" in texts(build_content(doc, "text"))


def test_system_prompt_follows_the_pack_conventions_and_guards_against_injection():
    assert "ROW of the invoice's item table" in SYSTEM_PROMPT and "NEGATIVE amount" in SYSTEM_PROMPT
    assert "use 0" in SYSTEM_PROMPT and "only in the totals block" in SYSTEM_PROMPT
    assert "untrusted data" in SYSTEM_PROMPT
    assert "JSON object" in SYSTEM_PROMPT and "tool" not in SYSTEM_PROMPT.lower()
    assert PROMPT_VERSION == "v1" and len(PROMPT_SHA) == 10
