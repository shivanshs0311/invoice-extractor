"""Turn a file on disk into something the LLM can read, or fail with a clear reason.

Handles: digital PDFs (text layer), scanned PDFs, phone photos (JPG/PNG/...), and the bad inputs
that should never reach the API: missing, empty, oversize, corrupt, encrypted, blank, unsupported.
"""
from __future__ import annotations

import base64
import io
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from collections.abc import Callable

try:  # PyMuPDF >= 1.24.3 exposes `pymupdf`; older releases only expose `fitz`.
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore[no-redef]

from PIL import Image, ImageOps, ImageSequence, ImageStat, UnidentifiedImageError

from .config import Settings

try:  # MuPDF prints repair noise to stderr; we report problems through IngestError and warnings instead
    fitz.TOOLS.mupdf_display_errors(False)
except Exception:  # pragma: no cover
    pass


class IngestError(Exception):
    """The input cannot be processed. `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PageImage:
    index: int
    media_type: str
    data_b64: str
    width: int
    height: int


@dataclass
class LoadedDocument:
    path: Path
    kind: str  # "pdf" | "image"
    page_count: int
    pages_used: int
    text: str  # machine-readable text layer ("" for images and scans)
    text_ok: bool  # True when the text layer looks complete and clean
    is_scan: bool  # True for photos and image-only or image-dominated PDFs
    warnings: list[str] = field(default_factory=list)
    _renderer: Optional[Callable[[], list[PageImage]]] = field(default=None, repr=False)
    _images: Optional[list[PageImage]] = field(default=None, repr=False)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    @property
    def source_type(self) -> str:
        if self.kind == "image":
            return "image"
        return "scanned_pdf" if self.is_scan or not self.text_ok else "digital_pdf"

    def images(self) -> list[PageImage]:
        if self._images is None:
            self._images = self._renderer() if self._renderer else []
        return self._images


# --------------------------------------------------------------------------- #
# Type sniffing (magic bytes beat file extensions: phone scans are often mislabelled)
# --------------------------------------------------------------------------- #
def sniff_kind(raw: bytes) -> Optional[str]:
    head = raw[:2048]
    if b"%PDF-" in head:
        return "pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image"
    if raw[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    if raw[:2] == b"BM":
        return "image"
    if raw[4:8] == b"ftyp" and raw[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis"):
        raise IngestError("unsupported_type", "HEIC/HEIF photos are not supported. Export the photo as JPG or PNG.")
    return None


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def load_document(path: str | Path, settings: Settings) -> LoadedDocument:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise IngestError("file_not_found", f"No such file: {p}")
    size = p.stat().st_size
    if size == 0:
        raise IngestError("empty_file", "The file is empty (0 bytes).")
    if size > settings.max_file_mb * 1024 * 1024:
        raise IngestError("file_too_large", f"File is {size / 1e6:.1f} MB; the limit is {settings.max_file_mb:g} MB.")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise IngestError("unreadable_file", f"Could not read the file: {exc}") from exc

    kind = sniff_kind(raw)
    if kind is None:
        raise IngestError(
            "unsupported_type",
            f"The file content is not a supported type (the name ends in {p.suffix or 'nothing'}, but the bytes are not "
            "a PDF or an image). Supported: PDF, PNG, JPG, WEBP, TIFF, BMP.",
        )
    if kind == "pdf":
        return _load_pdf(p, raw, settings)
    return _load_image(p, raw, settings)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _load_pdf(path: Path, raw: bytes, settings: Settings) -> LoadedDocument:
    try:
        pdf = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several exception types for broken files
        raise IngestError("corrupt_file", f"Cannot open PDF: {exc}") from exc

    try:
        if pdf.needs_pass:
            raise IngestError("encrypted_pdf", "The PDF is password protected.")
        page_count = pdf.page_count
        if page_count == 0:
            raise IngestError("no_pages", "The PDF has no pages.")

        warnings: list[str] = []
        if getattr(pdf, "is_repaired", False):
            warnings.append("repaired_pdf")  # damaged or truncated file that MuPDF patched up: content may be partial
        pages_used = min(page_count, settings.max_pages)
        if page_count > pages_used:
            warnings.append("truncated_pages")

        texts: list[str] = []
        coverage: list[float] = []
        try:
            for i in range(min(page_count, 20)):
                page = pdf[i]
                texts.append(_layout_text(page))
                if i < pages_used:
                    coverage.append(_image_coverage(page))
        except IngestError:
            raise
        except Exception as exc:
            raise IngestError("corrupt_file", f"PDF pages could not be read: {exc}") from exc
    finally:
        pdf.close()

    if any(t.strip() for t in texts):
        text = "".join(f"\n=== Page {i + 1} of {page_count} ===\n{t}\n" for i, t in enumerate(texts)).strip()
    else:
        text = ""
    if len(text) > settings.max_text_chars:
        text = text[: settings.max_text_chars]
        warnings.append("truncated_text")

    is_scan = any(c >= settings.scan_image_coverage for c in coverage)
    text_ok = _text_layer_ok("\n".join(texts), pages_used, settings)
    if is_scan and text_ok:
        warnings.append("scan_with_text_layer")  # likely OCR'd by a scanner app; images are more trustworthy
    if not text_ok and not is_scan:
        warnings.append("poor_text_layer")

    doc = LoadedDocument(
        path=path,
        kind="pdf",
        page_count=page_count,
        pages_used=pages_used,
        text=text,
        text_ok=text_ok,
        is_scan=is_scan,
        warnings=warnings,
    )
    doc._renderer = lambda: _render_pdf(raw, pages_used, settings)

    if not text_ok:
        # Nothing machine-readable: make sure there is actually something to look at before paying for an API call.
        images = doc.images()
        if all(_is_blank(img_b64) for img_b64 in (im.data_b64 for im in images)):
            raise IngestError("blank_document", "The document appears to be blank (no text and empty page images).")
    return doc


def _layout_text(page) -> str:
    """Rebuild reading-order text with columns kept apart, so table rows stay on one line."""
    words = page.get_text("words")
    if not words:
        return ""
    heights = [w[3] - w[1] for w in words if w[3] > w[1]]
    widths = [(w[2] - w[0]) / max(len(w[4]), 1) for w in words if w[2] > w[0]]
    if not heights or not widths:
        return page.get_text("text").strip()
    line_tol = 0.55 * statistics.median(heights)
    col_gap = 2.5 * statistics.median(widths)

    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list[tuple]] = []
    current = [words[0]]
    current_y = (words[0][1] + words[0][3]) / 2
    for w in words[1:]:
        yc = (w[1] + w[3]) / 2
        if abs(yc - current_y) <= line_tol:
            current.append(w)
            current_y = (current_y * (len(current) - 1) + yc) / len(current)
        else:
            lines.append(current)
            current, current_y = [w], yc
    lines.append(current)

    out = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        pieces: list[str] = []
        prev = None
        for w in line:
            if prev is not None:
                pieces.append(" | " if (w[0] - prev[2]) > col_gap else " ")
            pieces.append(w[4])
            prev = w
        out.append("".join(pieces))
    return "\n".join(out)


def _image_coverage(page) -> float:
    """Fraction of the page area covered by embedded images (about 1.0 for a scanned page)."""
    rect = page.rect
    area = rect.width * rect.height
    if area <= 0:
        return 0.0
    covered = 0.0
    try:
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                inter = fitz.Rect(r) & rect
                if not inter.is_empty:
                    covered += inter.width * inter.height
    except Exception:
        return 0.0
    return min(covered / area, 1.0)


def _text_layer_ok(text: str, pages: int, settings: Settings) -> bool:
    compact = re.sub(r"\s", "", text)
    if len(compact) < settings.min_text_chars_per_page * max(pages, 1):
        return False
    if "(cid:" in text:
        return False
    garbled = sum(1 for ch in compact if ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff")
    if garbled / len(compact) > 0.02:
        return False
    alnum = sum(1 for ch in compact if ch.isalnum())
    return alnum / len(compact) >= 0.5


def _render_pdf(raw: bytes, pages: int, settings: Settings) -> list[PageImage]:
    pdf = fitz.open(stream=raw, filetype="pdf")
    out: list[PageImage] = []
    try:
        for i in range(pages):
            page = pdf[i]
            longest = max(page.rect.width, page.rect.height) or 1.0
            zoom = min(max(settings.max_image_edge / longest, 0.25), 4.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out.append(_encode(img, i, settings))
    except Exception as exc:
        raise IngestError("corrupt_file", f"Could not render PDF pages: {exc}") from exc
    finally:
        pdf.close()
    return out


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def _load_image(path: Path, raw: bytes, settings: Settings) -> LoadedDocument:
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.load()
        frames = [f.copy() for f in ImageSequence.Iterator(probe)][: settings.max_pages]
        n_frames = getattr(probe, "n_frames", 1)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise IngestError("corrupt_file", f"Cannot decode image: {exc}") from exc

    warnings: list[str] = []
    prepared: list[Image.Image] = []
    for frame in frames:
        img = _normalise(frame)
        prepared.append(img)
    if not prepared:
        raise IngestError("corrupt_file", "Image has no frames.")
    if all(_stddev(im) < 4.0 for im in prepared):
        raise IngestError("blank_document", "The image appears to be blank.")
    if min(prepared[0].size) < 500:
        warnings.append("low_resolution")
    if n_frames > len(prepared):
        warnings.append("truncated_pages")

    images = [_encode(im, i, settings) for i, im in enumerate(prepared)]
    doc = LoadedDocument(
        path=path,
        kind="image",
        page_count=n_frames,
        pages_used=len(images),
        text="",
        text_ok=False,
        is_scan=True,
        warnings=warnings,
    )
    doc._images = images
    doc._renderer = lambda: images
    return doc


def _normalise(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # phone photos carry their rotation in EXIF
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return img.convert("RGB")


def _stddev(img: Image.Image) -> float:
    return ImageStat.Stat(img.convert("L")).stddev[0]


def _encode(img: Image.Image, index: int, settings: Settings) -> PageImage:
    if max(img.size) > settings.max_image_edge:
        img = img.copy()
        img.thumbnail((settings.max_image_edge, settings.max_image_edge), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=settings.jpeg_quality, optimize=True)
    return PageImage(
        index=index,
        media_type="image/jpeg",
        data_b64=base64.b64encode(buf.getvalue()).decode("ascii"),
        width=img.width,
        height=img.height,
    )


def _is_blank(data_b64: str) -> bool:
    img = Image.open(io.BytesIO(base64.b64decode(data_b64)))
    return _stddev(img) < 4.0
