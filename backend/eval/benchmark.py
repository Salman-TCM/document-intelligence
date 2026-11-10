"""Throughput on large PDFs (the brief mentions ~1000-page files).

python -m eval.benchmark --digital-pages 1000 --scanned-pages 100
"""

import argparse
import random
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.processing.extraction import extract
from app.processing.readers import read_document
from eval.generate_dataset import invoice_text, make_invoice, write_pdf, write_scanned_pdf


def run(path: Path, label: str) -> str:
    started = time.perf_counter()
    result = read_document(path)
    read_seconds = time.perf_counter() - started
    for segment in result.segments:
        segment.data or extract(segment.text)
    total = time.perf_counter() - started
    return (
        f"| {label} | {result.page_count} | {len(result.segments)} | {read_seconds:.1f}s | "
        f"{total:.1f}s | {result.page_count / total:.1f} |"
    )


def main(digital_pages: int, scanned_pages: int) -> None:
    rng = random.Random(1)
    pages = [invoice_text(make_invoice(rng, n), rng) for n in range(max(digital_pages, scanned_pages))]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        digital = Path(tmp) / "digital.pdf"
        write_pdf(digital, pages[:digital_pages])
        rows.append(run(digital, "digital PDF"))

        scanned = Path(tmp) / "scanned.pdf"
        write_scanned_pdf(scanned, pages[:scanned_pages], degrade=False)
        rows.append(run(scanned, f"scanned PDF ({settings.ocr_workers} OCR threads)"))

    print("| File | Pages | Invoices | Read/OCR | Total | Pages/s |")
    print("|---|---|---|---|---|---|")
    print("\n".join(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--digital-pages", type=int, default=1000)
    parser.add_argument("--scanned-pages", type=int, default=100)
    args = parser.parse_args()
    main(args.digital_pages, args.scanned_pages)
