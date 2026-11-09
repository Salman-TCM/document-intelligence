"""Reads uploaded files and splits them into invoice-sized segments.

A segment is the unit we extract one invoice from:
- PDFs and images: a run of pages that belong to the same invoice number.
- Spreadsheets with recognisable invoice columns: one segment per invoice number,
  already structured, so no extraction step is needed.
- Any other spreadsheet: one text segment per sheet.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import fitz
import pandas as pd
from PIL import Image, ImageSequence, UnidentifiedImageError

from app.config import settings
from app.processing.extraction import INVOICE_NUMBER, InvoiceData, LineItem, parse_amount, parse_date
from app.processing.ocr import ocr_image

FILE_TYPES = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".csv": "spreadsheet",
}

# A PDF page with less text than this is treated as a scan and sent to OCR.
MIN_TEXT_CHARS = 25
OCR_DPI = 300


class DocumentReadError(Exception):
    pass


@dataclass
class Segment:
    source: str
    text: str
    data: InvoiceData | None = None


@dataclass
class ReadResult:
    segments: list[Segment]
    page_count: int
    text: str


def file_type_for(filename: str) -> str | None:
    return FILE_TYPES.get(Path(filename).suffix.lower())


def read_document(path: str | Path) -> ReadResult:
    path = Path(path)
    file_type = file_type_for(path.name)
    if file_type == "spreadsheet":
        sheets = read_spreadsheet(path)
        segments = [seg for name, df in sheets.items() for seg in spreadsheet_segments(name, df)]
        text = "\n\n".join(seg.text for seg in segments)
        return ReadResult(segments, page_count=len(sheets), text=text)

    pages = read_pdf(path) if file_type == "pdf" else read_image(path)
    return ReadResult(split_pages(pages), page_count=len(pages), text="\n\n".join(pages))


# --- PDF and images ----------------------------------------------------------


def read_pdf(path: Path) -> list[str]:
    try:
        pdf = fitz.open(path)
    except Exception as exc:
        raise DocumentReadError("Could not open PDF: the file is damaged or not a PDF") from exc

    with pdf, ThreadPoolExecutor(settings.ocr_workers) as pool:
        if pdf.needs_pass:
            raise DocumentReadError("PDF is password protected")
        pages = [page.get_text().replace("\x00", "") for page in pdf]  # Postgres rejects NUL
        scanned = [i for i, text in enumerate(pages) if len(text.strip()) < MIN_TEXT_CHARS]

        # Render in small batches so a 1000-page scan doesn't sit in memory at once.
        # Tesseract runs as a subprocess, so threads give real parallelism here.
        for start in range(0, len(scanned), settings.ocr_workers):
            batch = scanned[start : start + settings.ocr_workers]
            images = [_render(pdf[i]) for i in batch]
            for i, text in zip(batch, pool.map(ocr_image, images)):
                pages[i] = text

    if not pages:
        raise DocumentReadError("PDF has no pages")
    return pages


def _render(page: fitz.Page) -> Image.Image:
    pixmap = page.get_pixmap(dpi=OCR_DPI, colorspace=fitz.csGRAY)
    return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)


def read_image(path: Path) -> list[str]:
    try:
        with Image.open(path) as image:
            # Multi-page TIFFs have one frame per page.
            return [ocr_image(frame.copy()) for frame in ImageSequence.Iterator(image)]
    except (UnidentifiedImageError, OSError) as exc:
        raise DocumentReadError("Could not read image: the file is damaged or not a supported image") from exc


def split_pages(pages: list[str]) -> list[Segment]:
    """Group consecutive pages by invoice number.

    A page that shows a new invoice number starts a new invoice; pages without one
    (continuation pages, terms and conditions) stay with the invoice before them.
    """
    segments: list[Segment] = []
    current_number = None
    first_page = 1
    for page_no, text in enumerate(pages, start=1):
        match = INVOICE_NUMBER.search(text)
        number = match.group(1) if match else None
        if segments and (number is None or number == current_number):
            segments[-1].text += "\n" + text
            segments[-1].source = f"pages {first_page}-{page_no}"
            continue
        segments.append(Segment(source=f"page {page_no}", text=text))
        current_number, first_page = number, page_no
    return segments


# --- Spreadsheets ------------------------------------------------------------

# Accepted header spellings for each field, compared after lowercasing and
# stripping everything but letters and digits.
COLUMN_ALIASES = {
    "invoice_number": {"invoicenumber", "invoiceno", "invoice", "invoiceid", "invno"},
    "invoice_date": {"invoicedate", "date"},
    "supplier_name": {"supplier", "suppliername", "vendor", "vendorname", "seller"},
    "customer_name": {"customer", "customername", "client", "billto", "buyer"},
    "subtotal": {"subtotal", "net", "netamount"},
    "tax": {"tax", "vat", "gst", "taxamount"},
    "total": {"total", "totalamount", "grandtotal", "amountdue", "gross"},
    "currency": {"currency", "curr"},
    "description": {"description", "item", "product", "service"},
    "quantity": {"quantity", "qty"},
    "unit_price": {"unitprice", "price", "rate"},
    "amount": {"amount", "linetotal", "lineamount"},
}


def read_spreadsheet(path: Path) -> dict[str, pd.DataFrame]:
    try:
        if path.suffix.lower() == ".csv":
            return {"csv": pd.read_csv(path, dtype=str, encoding_errors="replace")}
        return pd.read_excel(path, sheet_name=None, dtype=str)
    except Exception as exc:
        raise DocumentReadError("Could not read spreadsheet: the file is damaged or in an unsupported format") from exc


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    mapping = {}
    for column in df.columns:
        key = re.sub(r"[^a-z0-9]", "", str(column).lower())
        for field, aliases in COLUMN_ALIASES.items():
            if key in aliases and field not in mapping:
                mapping[field] = column
    return mapping


def spreadsheet_segments(sheet: str, df: pd.DataFrame) -> list[Segment]:
    df = df.dropna(how="all")
    if df.empty:
        return []

    columns = _map_columns(df)
    if "invoice_number" not in columns:
        return [Segment(source=f"sheet {sheet}", text=df.to_csv(index=False))]

    df = df.dropna(subset=[columns["invoice_number"]])
    segments = []
    for number, rows in df.groupby(columns["invoice_number"], sort=False):
        segments.append(
            Segment(
                source=f"sheet {sheet}",
                text=rows.to_csv(index=False),
                data=_invoice_from_rows(str(number), rows, columns),
            )
        )
    return segments


def _cell(row: pd.Series, columns: dict[str, str], field: str) -> str | None:
    column = columns.get(field)
    if column is None or pd.isna(row[column]):
        return None
    return str(row[column]).strip()


def _invoice_from_rows(number: str, rows: pd.DataFrame, columns: dict[str, str]) -> InvoiceData:
    first = rows.iloc[0]
    line_items = []
    if "description" in columns:
        line_items = [
            LineItem(
                description=_cell(row, columns, "description"),
                quantity=parse_amount(_cell(row, columns, "quantity")),
                unit_price=parse_amount(_cell(row, columns, "unit_price")),
                amount=parse_amount(_cell(row, columns, "amount")),
            )
            for _, row in rows.iterrows()
        ]

    invoice_date = _cell(first, columns, "invoice_date")
    return InvoiceData(
        invoice_number=number.strip(),
        invoice_date=parse_date(invoice_date) if invoice_date else None,
        supplier_name=_cell(first, columns, "supplier_name"),
        customer_name=_cell(first, columns, "customer_name"),
        subtotal=parse_amount(_cell(first, columns, "subtotal")),
        tax=parse_amount(_cell(first, columns, "tax")),
        total=parse_amount(_cell(first, columns, "total")),
        currency=_cell(first, columns, "currency"),
        line_items=line_items,
    )
