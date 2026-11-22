#!/usr/bin/env python3
"""Make harder copies of the labelled documents, so the eval has something to find.

  python scripts/stress.py                      writes data/stress/ : 3 damage levels for every labelled document
  python eval.py --data-dir data/stress --tag stress

Each copy is an image-only PDF (like a bad phone scan) that is downscaled, blurred, noisy, tilted and
heavily JPEG compressed. The label file is copied alongside, so the normal eval works on it. This is a
stress test of robustness, not a replacement for real data, and it is reported as such.
"""
from __future__ import annotations

import argparse
import base64
import io
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from PIL import Image, ImageEnhance, ImageFilter

from invoice_extractor.config import load_settings
from invoice_extractor.ingest import IngestError, load_document

LEVELS = {
    "mild": dict(angle=2.0, blur=0.8, noise=0.05, width=1100, jpeg=60),
    "medium": dict(angle=4.0, blur=1.6, noise=0.10, width=800, jpeg=40),
    "severe": dict(angle=6.0, blur=2.6, noise=0.16, width=520, jpeg=25),
}


def degrade(img: Image.Image, *, angle: float, blur: float, noise: float, width: int, jpeg: int, rng: random.Random) -> bytes:
    img = img.convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(0.85)
    if noise:
        img = Image.blend(img, Image.effect_noise(img.size, 30).convert("RGB"), noise)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur))
    img = img.rotate(angle * rng.choice([-1, 1]), expand=True, fillcolor=(236, 236, 232), resample=Image.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=str(ROOT / "data" / "sample_pack" / "labelled"), help="Folder with labelled documents and their .json labels")
    ap.add_argument("--out", default=str(ROOT / "data" / "stress"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    pack, out = Path(args.pack), Path(args.out)
    labels = sorted(pack.glob("*.json"))
    if not labels:
        print(f"No label files in {pack}")
        return 1
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    settings = load_settings()
    written = 0
    for label in labels:
        source = next((p for p in pack.iterdir() if p.stem == label.stem and p.suffix.lower() != ".json"), None)
        if source is None:
            continue
        try:
            pages = load_document(source, settings).images()
        except IngestError as exc:
            print(f"skip {source.name}: {exc.message}")
            continue
        for level, params in LEVELS.items():
            rng = random.Random(f"{args.seed}-{label.stem}-{level}")
            doc = fitz.open()
            for page_image in pages:
                img = Image.open(io.BytesIO(base64.b64decode(page_image.data_b64)))
                jpg = degrade(img, rng=rng, **params)
                page = doc.new_page(width=595, height=842)
                page.insert_image(page.rect, stream=jpg)
            name = f"{label.stem}_{level}"
            (out / f"{name}.pdf").write_bytes(doc.tobytes())
            shutil.copy(label, out / f"{name}.json")
            written += 1
    print(f"Wrote {written} stress documents (+ labels) to {out}")
    print("Next: python eval.py --data-dir data\\stress --tag stress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
