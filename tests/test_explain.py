import re
from pathlib import Path

from invoice_extractor.explain import explain_failure, explain_review, known_failure_codes

PKG = Path(__file__).resolve().parent.parent / "invoice_extractor"


def _codes_raised_in_code() -> set[str]:
    """Every failure code the pipeline can produce, read from the source so a new one cannot slip by."""
    ingest = set(re.findall(r'IngestError\(\s*"([a-z_]+)"', (PKG / "ingest.py").read_text()))
    llm = {f"api_{k}" for k in re.findall(r'LLMError\(\s*"([a-z_]+)"', (PKG / "llm.py").read_text())}
    llm |= {f"api_{k}" for k in re.findall(r'kind\s*=\s*"([a-z_]+)"', (PKG / "llm.py").read_text())}
    pipeline = set(re.findall(r'_failed\(\s*"([a-z_]+)"', (PKG / "pipeline.py").read_text())) | {"invalid_output"}
    return ingest | llm | pipeline


def test_every_failure_code_has_a_plain_language_explanation():
    missing = _codes_raised_in_code() - known_failure_codes()
    assert not missing, f"add these to explain.py: {sorted(missing)}"


def test_explanation_has_title_why_and_fix():
    e = explain_failure("encrypted_pdf")
    assert e["code"] == "encrypted_pdf" and "password" in e["title"].lower() and e["why"] and e["fix"]


def test_unknown_code_still_gets_a_readable_explanation():
    e = explain_failure("something_new")
    assert e["title"] and e["fix"] and e["code"] == "something_new"


def test_review_reasons_become_sentences_and_failure_markers_are_dropped():
    sentences = explain_review(["totals_reconcile", "extraction_failed:corrupt_file", "new_check"])
    assert len(sentences) == 2 and "add up" in sentences[0] and sentences[1] == "new_check"
