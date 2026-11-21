import pytest
from PIL import Image

from factories import digital_pdf, garbage_pdf, locked_pdf, photo_jpg, scanned_pdf
from invoice_extractor.config import Settings
from invoice_extractor.ingest import IngestError, load_document, sniff_kind

S = Settings()


def test_digital_pdf_has_layout_text(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf"), S)
    assert doc.source_type == "digital_pdf" and doc.text_ok and not doc.is_scan
    assert "A4 paper, 500 sheets | 10 | 320.00 | 3,200.00" in doc.text  # a table row stays on one line
    assert "SOS/2026/0412" in doc.text


def test_multipage_pdf_reads_all_pages(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf", pages=2), S)
    assert doc.page_count == 2 and doc.pages_used == 2
    assert "Page 2 of 2" in doc.text


def test_page_cap_adds_a_warning(tmp_path):
    doc = load_document(digital_pdf(tmp_path / "a.pdf", pages=3), S.with_overrides(max_pages=1))
    assert doc.pages_used == 1 and "truncated_pages" in doc.warnings


def test_scanned_pdf_is_detected_and_rendered(tmp_path):
    doc = load_document(scanned_pdf(tmp_path / "s.pdf"), S)
    assert doc.is_scan and not doc.text_ok and doc.source_type == "scanned_pdf"
    images = doc.images()
    assert len(images) == 1 and max(images[0].width, images[0].height) <= S.max_image_edge
    assert images[0].media_type == "image/jpeg"


def test_photo_is_an_image_document(tmp_path):
    doc = load_document(photo_jpg(tmp_path / "p.jpg"), S)
    assert doc.kind == "image" and doc.source_type == "image" and doc.images()


def test_exif_rotation_is_applied(tmp_path):
    img = Image.new("RGB", (1200, 800), (255, 255, 255))
    for x in range(100, 500):
        for y in range(100, 140):
            img.putpixel((x, y), (0, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    path = tmp_path / "phone.jpg"
    img.save(path, exif=exif)
    doc = load_document(path, S)
    assert (doc.images()[0].width, doc.images()[0].height) == (800, 1200)


def test_file_type_comes_from_content_not_extension(tmp_path):
    renamed = tmp_path / "scan.pdf"
    renamed.write_bytes(photo_jpg(tmp_path / "p.jpg").read_bytes())
    assert load_document(renamed, S).kind == "image"


def test_bad_inputs_raise_specific_codes(tmp_path):
    (tmp_path / "empty.pdf").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("not a pdf", encoding="utf-8")
    Image.new("RGB", (900, 1200), (255, 255, 255)).save(tmp_path / "blank.png")
    garbage_pdf(tmp_path / "garbage.pdf")
    locked_pdf(tmp_path / "locked.pdf")
    cases = {
        "empty.pdf": "empty_file",
        "notes.txt": "unsupported_type",
        "blank.png": "blank_document",
        "garbage.pdf": "corrupt_file",
        "locked.pdf": "encrypted_pdf",
    }
    for name, code in cases.items():
        with pytest.raises(IngestError) as err:
            load_document(tmp_path / name, S)
        assert err.value.code == code, name


def test_a_truncated_pdf_never_passes_silently(tmp_path):
    """MuPDF repairs broken files, so depending on where it was cut we get an error or a repaired file with a warning."""
    raw = digital_pdf(tmp_path / "good.pdf").read_bytes()
    for fraction in (0.2, 0.33, 0.5, 0.7, 0.9):
        path = tmp_path / f"cut_{fraction}.pdf"
        path.write_bytes(raw[: int(len(raw) * fraction)])
        try:
            doc = load_document(path, S)
        except IngestError:
            continue  # rejected: fine
        assert "repaired_pdf" in doc.warnings, fraction  # opened: it must carry the warning


def test_missing_and_oversize(tmp_path):
    with pytest.raises(IngestError) as err:
        load_document(tmp_path / "nope.pdf", S)
    assert err.value.code == "file_not_found"
    big = digital_pdf(tmp_path / "big.pdf")
    with pytest.raises(IngestError) as err:
        load_document(big, S.with_overrides(max_file_mb=0.001))
    assert err.value.code == "file_too_large"


def test_heic_is_rejected_with_advice():
    with pytest.raises(IngestError) as err:
        sniff_kind(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 30)
    assert "JPG" in str(err.value)


def test_low_resolution_photo_warns(tmp_path):
    img = Image.new("RGB", (400, 300), (250, 250, 250))
    for x in range(20, 300):
        for y in range(20, 30):
            img.putpixel((x, y), (0, 0, 0))
    path = tmp_path / "tiny.png"
    img.save(path)
    assert "low_resolution" in load_document(path, S).warnings
