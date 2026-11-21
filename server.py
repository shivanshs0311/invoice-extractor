"""Small API plus the review frontend.

  python -m uvicorn server:app --port 8000      then open http://127.0.0.1:8000

POST /api/extract   multipart upload (field name: file) -> {"output": {...}, "meta": {...}}
GET  /api/health    which models and mode are configured
GET  /              the upload page
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


def create_app(settings: Optional[Settings] = None, client: Optional[LLMClient] = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Invoice extractor", docs_url="/docs", redoc_url=None)
    lazy = _LazyClient(settings, client)

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
    async def extract(file: UploadFile = File(...)):
        data = await file.read()
        if len(data) > settings.max_file_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_file_mb:g} MB.")
        suffix = Path(file.filename or "").suffix.lower()[:8]
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(data)
            handle.close()
            result = await run_in_threadpool(extract_document, handle.name, settings, lazy)
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        meta = dict(result.meta)
        if isinstance(meta.get("error"), dict):
            meta["error"] = {k: v for k, v in meta["error"].items() if k != "detail"}  # no stack traces to the browser
        return {"output": result.output, "meta": meta}

    return app


app = create_app()
