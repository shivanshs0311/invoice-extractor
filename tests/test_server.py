import pytest
from fastapi.testclient import TestClient

from factories import digital_pdf, garbage_pdf
from fakes import FakeClient, good_payload
from invoice_extractor.config import Settings
from invoice_extractor.history import History
from server import create_app

S = Settings(api_backoff_s=0.0)


@pytest.fixture
def make_http(tmp_path):
    def build(handler=lambda *a: good_payload(), settings=S, client="fake"):
        fake = FakeClient(handler) if client == "fake" else None
        return TestClient(create_app(settings, fake, History(tmp_path / "history")))

    return build


def upload(http, path, name="a.pdf"):
    return http.post("/api/extract", files={"file": (name, path.read_bytes(), "application/pdf")})


def test_extract_endpoint_returns_output_meta_and_no_failure(make_http, tmp_path):
    with make_http() as http:
        body = upload(http, digital_pdf(tmp_path / "inv.pdf")).json()
    assert body["output"]["total"] == 17750.0 and body["output"]["needs_review"] is False
    assert body["meta"]["status"] == "ok" and body["meta"]["cost_usd"] > 0
    assert body["failure"] is None and body["review"] == [] and body["id"] == 1


def test_bad_file_gets_a_plain_language_explanation(make_http, tmp_path):
    with make_http() as http:
        r = upload(http, garbage_pdf(tmp_path / "garbage.pdf"), "x.pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["status"] == "failed" and body["output"]["error"]["code"] == "corrupt_file"
    assert body["failure"]["title"] == "The file is damaged" and body["failure"]["fix"]
    assert "detail" not in body["meta"]["error"]  # no stack traces to the browser


def test_review_reasons_are_explained(make_http, tmp_path):
    with make_http(lambda *a: good_payload(total=99999.0)) as http:  # totals cannot reconcile, even on the retry
        body = upload(http, digital_pdf(tmp_path / "inv.pdf")).json()
    assert body["output"]["needs_review"] is True
    assert any("do not add up" in sentence for sentence in body["review"])


def test_missing_api_key_surfaces_as_failed_extraction(make_http, tmp_path):
    with make_http(client=None) as http:  # real lazy client, no key in the environment
        body = upload(http, digital_pdf(tmp_path / "inv.pdf")).json()
    assert body["output"]["error"]["code"] == "api_auth" and "GEMINI_API_KEY" in body["failure"]["fix"]


def test_history_lists_shows_serves_and_deletes_uploads(make_http, tmp_path):
    pdf = digital_pdf(tmp_path / "inv.pdf")
    with make_http() as http:
        first = upload(http, pdf, "first.pdf").json()
        upload(http, garbage_pdf(tmp_path / "g.pdf"), "broken.pdf")
        items = http.get("/api/history").json()["items"]
        assert [i["filename"] for i in items] == ["broken.pdf", "first.pdf"]  # newest first
        assert items[0]["status"] == "failed" and items[0]["error_code"] == "corrupt_file"
        assert items[0]["failure_title"] == "The file is damaged" and items[1]["failure_title"] is None
        assert items[1]["vendor"] == "Sharma Office Supplies Pvt Ltd" and items[1]["total"] == 17750.0

        again = http.get(f"/api/history/{first['id']}").json()
        assert again["output"] == first["output"] and again["filename"] == "first.pdf"
        assert http.get(f"/api/history/{first['id']}/file").content == pdf.read_bytes()

        assert http.delete(f"/api/history/{first['id']}").json() == {"deleted": first["id"]}
        assert http.get(f"/api/history/{first['id']}").status_code == 404
        assert len(http.get("/api/history").json()["items"]) == 1


def test_size_limit_health_and_index(make_http):
    with make_http(settings=S.with_overrides(max_file_mb=0.0001)) as http:
        r = http.post("/api/extract", files={"file": ("a.pdf", b"x" * 5000)})
        assert r.status_code == 413 and "limit" in r.json()["detail"]
        health = http.get("/api/health").json()
        assert health["ok"] is True and health["model"] == S.model
        assert http.get("/").status_code == 200
