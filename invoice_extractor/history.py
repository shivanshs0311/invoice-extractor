"""History of every document processed through the API: results, review flags, errors and the original file.

SQLite (built into Python) keeps one row per upload, and the uploaded file is kept next to it so a reviewer can
open the original again later. Everything lives under data/history/, which is git-ignored, because invoices are
confidential.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .pipeline import ExtractionResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_file TEXT,
    status TEXT NOT NULL,
    vendor TEXT,
    invoice_number TEXT,
    total REAL,
    currency TEXT,
    error_code TEXT,
    cost_usd REAL,
    output_json TEXT NOT NULL,
    meta_json TEXT NOT NULL
)
"""

# Columns shown in the history list (the full JSON is only loaded for one record at a time).
_SUMMARY = (
    "id, created_at, filename, status, json_extract(output_json, '$.is_invoice') AS is_invoice, "
    "vendor, invoice_number, total, currency, error_code, cost_usd"
)


class History:
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.files = self.folder / "files"
        self.files.mkdir(parents=True, exist_ok=True)
        self.db_path = self.folder / "history.db"
        with closing(self._connect()) as db, db:
            db.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)  # one short connection per call: safe across server threads
        db.row_factory = sqlite3.Row
        return db

    def add(self, filename: str, data: bytes, result: ExtractionResult) -> int:
        out, meta = result.output, _browser_safe(result.meta)
        row = (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            filename,
            result.status,
            out.get("vendor"),
            out.get("invoice_number"),
            out.get("total"),
            out.get("currency"),
            (out.get("error") or {}).get("code"),
            meta.get("cost_usd"),
            json.dumps(out, ensure_ascii=False),
            json.dumps(meta, ensure_ascii=False),
        )
        with closing(self._connect()) as db, db:
            record_id = db.execute(
                "INSERT INTO uploads (created_at, filename, status, vendor, invoice_number, total, currency, "
                "error_code, cost_usd, output_json, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            ).lastrowid
            stored = f"{record_id}{Path(filename).suffix.lower()[:8]}"
            (self.files / stored).write_bytes(data)
            db.execute("UPDATE uploads SET stored_file = ? WHERE id = ?", (stored, record_id))
        return record_id

    def list(self, limit: int = 200) -> list[dict]:
        with closing(self._connect()) as db:
            rows = db.execute(f"SELECT {_SUMMARY} FROM uploads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        items = [dict(r) for r in rows]
        for item in items:  # SQLite stores JSON booleans as 1/0 (and null stays None)
            if item["is_invoice"] is not None:
                item["is_invoice"] = bool(item["is_invoice"])
        return items

    def get(self, record_id: int) -> Optional[dict]:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM uploads WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["output"] = json.loads(record.pop("output_json"))
        record["meta"] = json.loads(record.pop("meta_json"))
        return record

    def file_path(self, record_id: int) -> Optional[Path]:
        record = self.get(record_id)
        if not record or not record["stored_file"]:
            return None
        path = self.files / record["stored_file"]
        return path if path.exists() else None

    def delete(self, record_id: int) -> bool:
        path = self.file_path(record_id)
        with closing(self._connect()) as db, db:
            deleted = db.execute("DELETE FROM uploads WHERE id = ?", (record_id,)).rowcount > 0
        if path:
            path.unlink(missing_ok=True)
        return deleted


def _browser_safe(meta: dict) -> dict:
    """Drop stack traces: they help a developer in the logs, not a person reading the history."""
    meta = dict(meta)
    if isinstance(meta.get("error"), dict):
        meta["error"] = {k: v for k, v in meta["error"].items() if k != "detail"}
    return meta
