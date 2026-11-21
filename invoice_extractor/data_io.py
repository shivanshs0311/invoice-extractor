"""Find documents and ground-truth labels, tolerating different folder layouts.

Documents: every PDF/image under the data directory.
Labels, in order of preference:
  1. a per-document JSON next to or below the data dir whose name matches the document
     (invoice_01.json, invoice_01_gt.json, invoice_01.pdf.json, labels/invoice_01.json ...)
  2. one combined JSON: {"invoice_01.pdf": {...}, ...} or [{"file": "invoice_01.pdf", ...}, ...]
Label files must contain the assignment schema (at least an "is_invoice" key, possibly wrapped
under one key such as "ground_truth" or "expected").
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

DOC_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
SKIP_DIRS = {".git", "outputs", "reports", "__pycache__", ".venv", "venv", "node_modules"}
_LABEL_NOISE = re.compile(r"(^(gt|label|labels|truth|expected)[_\-.]|[_\-.](gt|label|labels|truth|ground[_\-]?truth|expected)$)", re.I)
FILE_KEYS = ("file", "filename", "file_name", "document", "doc", "name", "path")


def _walk(root: Path):
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if p.is_file():
            yield p


def discover_documents(path: str | Path) -> list[Path]:
    """A file returns itself; a directory returns every supported document under it."""
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.is_dir():
        return []
    return [f for f in _walk(p) if f.suffix.lower() in DOC_EXTENSIONS]


def _norm_stem(name: str) -> str:
    stem = name
    for _ in range(3):  # strip "x.pdf.json" and "x_gt" style decorations
        before = stem
        stem = Path(stem).stem if Path(stem).suffix.lower() in DOC_EXTENSIONS | {".json"} else stem
        stem = _LABEL_NOISE.sub("", stem)
        if stem == before:
            break
    return re.sub(r"[\W_]+", "", stem).lower()


def _unwrap(obj: Any) -> Optional[dict]:
    if not isinstance(obj, dict):
        return None
    if "is_invoice" in obj:
        return obj
    inner = [v for v in obj.values() if isinstance(v, dict) and "is_invoice" in v]
    return inner[0] if len(inner) == 1 else None


def _load_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def load_labels(data_dir: str | Path, labels: Optional[str | Path] = None) -> dict[Path, dict]:
    """Return {document_path: ground_truth_dict} for every document that has a label."""
    root = Path(data_dir)
    docs = discover_documents(root)
    by_key = {_norm_stem(d.name): d for d in docs}
    found: dict[Path, dict] = {}

    sources: list[Path] = []
    if labels:
        lp = Path(labels)
        sources = [lp] if lp.is_file() else [f for f in _walk(lp) if f.suffix.lower() == ".json"]
    else:
        sources = [f for f in _walk(root) if f.suffix.lower() == ".json" and not f.name.startswith("_") and f.name.lower() != "schema.json"]

    for src in sources:
        data = _load_json(src)
        if data is None:
            continue
        # Combined file: mapping filename -> label, or a list of labels carrying a filename key.
        if isinstance(data, dict) and "is_invoice" not in data and any(_norm_stem(str(k)) in by_key for k in data):
            for key, value in data.items():
                label = _unwrap(value)
                doc = by_key.get(_norm_stem(str(key)))
                if label is not None and doc is not None:
                    found[doc] = label
            continue
        if isinstance(data, list):
            for entry in data:
                label = _unwrap(entry)
                if label is None:
                    continue
                name = next((entry[k] for k in FILE_KEYS if isinstance(entry.get(k), str)), None)
                doc = by_key.get(_norm_stem(name)) if name else None
                if doc is not None:
                    found[doc] = label
            continue
        # Per-document file: match by name, or by an embedded filename.
        label = _unwrap(data)
        if label is None:
            continue
        doc = by_key.get(_norm_stem(src.name))
        if doc is None and isinstance(data, dict):
            name = next((data[k] for k in FILE_KEYS if isinstance(data.get(k), str)), None)
            doc = by_key.get(_norm_stem(name)) if name else None
        if doc is not None:
            found[doc] = label
    return dict(sorted(found.items(), key=lambda kv: kv[0].name))
