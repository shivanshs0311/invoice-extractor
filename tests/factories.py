"""Tiny file factories for tests, so no real data is needed."""
import io
import random
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from PIL import Image, ImageEnhance, ImageFilter

ROWS = [("A4 paper, 500 sheets", "10", "320.00", "3,200.00"), ("Laser printer toner", "3", "4,850.00", "14,550.00")]


def _digital_doc(pages: int = 1):
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((40, 60), "Sharma Office Supplies Pvt Ltd", fontsize=16)
        page.insert_text((40, 90), f"Invoice No: SOS/2026/0412   Page {number}", fontsize=10)
        y = 130
        for desc, qty, rate, amount in ROWS:
            page.insert_text((40, y), desc, fontsize=10)
            page.insert_text((330, y), qty, fontsize=10)
            page.insert_text((420, y), rate, fontsize=10)
            page.insert_text((500, y), amount, fontsize=10)
            y += 20
        page.insert_text((400, y + 20), "Total  Rs. 17,750.00", fontsize=11)
    return doc


def digital_pdf(path: Path, pages: int = 1) -> Path:
    path.write_bytes(_digital_doc(pages).tobytes())
    return path


def _scan_image(angle: float = 2.0) -> Image.Image:
    pix = _digital_doc()[0].get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = Image.blend(img, Image.effect_noise(img.size, 28).convert("RGB"), 0.07)
    img = ImageEnhance.Contrast(img).enhance(0.88).filter(ImageFilter.GaussianBlur(radius=0.7))
    return img.rotate(angle, expand=True, fillcolor=(238, 238, 234), resample=Image.BICUBIC)


def scanned_pdf(path: Path) -> Path:
    """A PDF whose only content is a page-sized picture, like a scanner app produces."""
    buf = io.BytesIO()
    _scan_image().save(buf, format="JPEG", quality=80)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    path.write_bytes(doc.tobytes())
    return path


def photo_jpg(path: Path) -> Path:
    _scan_image(angle=-2.5).save(path, format="JPEG", quality=82)
    return path


def locked_pdf(path: Path) -> Path:
    _digital_doc().save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    return path


def garbage_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n" + bytes(random.Random(3).randrange(256) for _ in range(600)))
    return path
