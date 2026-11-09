"""Builders for the sample files used in tests."""

import random
from pathlib import Path

import fitz
from PIL import Image, ImageFilter

INVOICE_TEXT = """\
From: ACME Supplies Ltd
INVOICE
Invoice No: INV-1001
Date: 2024-03-15
Bill To: Globex Corporation

Description          Qty   Unit Price   Amount
Widget A             2     50.00        100.00
Service fee          1     25.00        25.00

Subtotal 125.00
Tax (10%) 12.50
Total USD 137.50
"""


def invoice_text(number="INV-1001", total="137.50") -> str:
    return INVOICE_TEXT.replace("INV-1001", number).replace("137.50", total)


def make_pdf(path: Path, pages: list[str]) -> Path:
    with fitz.open() as pdf:
        for text in pages:
            page = pdf.new_page()
            page.insert_text((50, 72), text, fontname="cour", fontsize=11)
        pdf.save(path)
    return path


def render_image(text: str, degrade: bool = False) -> Image.Image:
    """Rasterise invoice text like a scanner would; `degrade` makes it a bad scan."""
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 72), text, fontname="cour", fontsize=11)
        pixmap = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    if degrade:
        rng = random.Random(42)
        image = image.rotate(1.5, fillcolor=255, expand=True)
        image = image.resize((image.width * 2 // 3, image.height * 2 // 3))
        image = image.filter(ImageFilter.GaussianBlur(0.8))
        noise = image.load()
        for _ in range(image.width * image.height // 50):
            noise[rng.randrange(image.width), rng.randrange(image.height)] = rng.choice((0, 255))
    return image


def make_scanned_pdf(path: Path, pages: list[str]) -> Path:
    with fitz.open() as pdf:
        for text in pages:
            image_path = path.with_suffix(".tmp.png")
            render_image(text).save(image_path)
            page = pdf.new_page()
            page.insert_image(page.rect, filename=str(image_path))
            image_path.unlink()
        pdf.save(path)
    return path
