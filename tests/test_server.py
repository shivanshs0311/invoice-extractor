from fastapi.testclient import TestClient

from factories import digital_pdf, garbage_pdf
from fakes import FakeClient, good_payload
from invoice_extractor.config import Settings
from server import create_app

S = Settings(api_backoff_s=0.0)


def test_extract_endpoint_returns_output_and_meta(tmp_path):
    pdf = digital_pdf(tmp_path / "inv.pdf")
    app = create_app(S, FakeClient(lambda n, m, c: good_payload()))
    with TestClient(app) as http:
        with open(pdf, "rb") as fh:
            r = http.post("/api/extract", files={"file": ("a.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["output"]["total"] == 17750.0 and body["output"]["needs_review"] is False
    assert body["meta"]["status"] == "ok" and body["meta"]["cost_usd"] > 0


def test_bad_file_returns_a_clear_error_not_a_500(tmp_path):
    bad = garbage_pdf(tmp_path / "garbage.pdf")
    app = create_app(S, FakeClient(lambda *a: {}))
    with TestClient(app) as http:
        r = http.post("/api/extract", files={"file": ("x.pdf", bad.read_bytes())})
    assert r.status_code == 200
    out = r.json()
    assert out["meta"]["status"] == "failed" and out["output"]["error"]["code"] == "corrupt_file"
    assert "detail" not in out["meta"]["error"]  # no stack traces to the browser


def test_missing_api_key_surfaces_as_failed_extraction(tmp_path):
    pdf = digital_pdf(tmp_path / "inv.pdf")
    app = create_app(S)  # real lazy client, no key in the environment
    with TestClient(app) as http:
        r = http.post("/api/extract", files={"file": ("a.pdf", pdf.read_bytes())})
    assert r.json()["output"]["error"]["code"] == "api_auth"
    assert "GEMINI_API_KEY" in r.json()["output"]["error"]["message"]


def test_size_limit_health_and_index():
    app = create_app(S.with_overrides(max_file_mb=0.0001), FakeClient(lambda *a: {}))
    with TestClient(app) as http:
        assert http.post("/api/extract", files={"file": ("a.pdf", b"x" * 5000)}).status_code == 413
        health = http.get("/api/health").json()
        assert health["ok"] is True and health["model"] == S.model
        assert http.get("/").status_code == 200
