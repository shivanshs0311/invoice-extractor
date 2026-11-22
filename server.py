"""Small API plus the review frontend.

  python -m uvicorn server:app --port 8000      then open http://127.0.0.1:8000

POST   /api/extract             multipart upload (field name: file), saved to the history
GET    /api/history             previous uploads, newest first
GET    /api/history/{id}        one upload with its full result
GET    /api/history/{id}/file   the original uploaded file
DELETE /api/history/{id}        remove one upload and its file
GET    /api/health              which models and mode are configured
GET    /                        the upload page

Every result carries plain-language text: `failure` (what went wrong, why, what to do) and `review` (why a
document needs a human look), so the page never has to show a raw error code.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from invoice_extractor.config import ROOT, Settings, load_settings
from invoice_extractor.explain import explain_failure, explain_review
from invoice_extractor.history import History
from invoice_extractor.llm import LLMClient, make_client
from invoice_extractor.pipeline import extract_document


class _LazyClient:
    """Builds the real client on first use, so bad files are rejected before any API key is needed."""

    def __init__(self, settings: Settings, client: Optional[LLMClient] = None):
        self._settings = settings
        self._client = client
        self._lock = threading.Lock()

    def extract(self, **kwargs):
        with self._lock:
            if self._client is None:
                self._client = make_client(self._settings)
        return self._client.extract(**kwargs)


def present(record: dict) -> dict:
    """The shape the page receives, for a fresh upload and for a history record alike."""
    output, meta = record["output"], record["meta"]
    error = output.get("error")
    failure = {**explain_failure(error.get("code")), "detail": error.get("message")} if error else None
    return {
        "id": record["id"],
        "filename": record["filename"],
        "created_at": record["created_at"],
        "output": output,
        "meta": meta,
        "failure": failure,
        "review": explain_review(output.get("review_reasons")),
    }


def create_app(
    settings: Optional[Settings] = None,
    client: Optional[LLMClient] = None,
    history: Optional[History] = None,
) -> FastAPI:
    settings = settings or load_settings()
    history = history or History(os.getenv("HISTORY_DIR") or ROOT / "data" / "history")
    app = FastAPI(title="Invoice extractor", docs_url="/docs", redoc_url=None)
    lazy = _LazyClient(settings, client)

    def find(record_id: int) -> dict:
        record = history.get(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="That record does not exist (it may have been deleted).")
        return record

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "model": settings.model,
            "escalation_model": settings.escalation_model if settings.escalate else None,
            "mode": settings.mode,
            "max_file_mb": settings.max_file_mb,
        }

    @app.post("/api/extract")
    async def extract(file: UploadFile = File(...)):  # noqa: B008 (FastAPI's way to declare an upload)
        data = await file.read()
        if len(data) > settings.max_file_mb * 1024 * 1024:
            text = explain_failure("file_too_large")
            raise HTTPException(status_code=413, detail=f"{text['title']}: the limit is {settings.max_file_mb:g} MB. {text['fix']}")
        name = Path(file.filename or "upload").name
        with tempfile.TemporaryDirectory() as tmp:  # the pipeline reads from a path; the folder is removed afterwards
            path = Path(tmp) / f"upload{Path(name).suffix.lower()[:8]}"
            path.write_bytes(data)
            result = await run_in_threadpool(extract_document, path, settings, lazy)
        record_id = history.add(name, data, result)
        return present(history.get(record_id))

    @app.get("/api/history")
    def list_history(limit: int = 200):
        items = history.list(limit=limit)
        for item in items:  # a readable reason in the list itself, so nobody has to open a record to see why it failed
            item["failure_title"] = explain_failure(item["error_code"])["title"] if item["error_code"] else None
        return {"items": items}

    @app.get("/api/history/{record_id}")
    def get_history(record_id: int):
        return present(find(record_id))

    @app.get("/api/history/{record_id}/file")
    def get_file(record_id: int):
        record = find(record_id)
        path = history.file_path(record_id)
        if path is None:
            raise HTTPException(status_code=404, detail="The original file is no longer stored.")
        return FileResponse(path, filename=record["filename"], content_disposition_type="inline")

    @app.delete("/api/history/{record_id}")
    def delete_history(record_id: int):
        find(record_id)
        history.delete(record_id)
        return {"deleted": record_id}

    return app


app = create_app()
