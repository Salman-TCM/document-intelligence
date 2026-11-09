import pandas as pd
import pytest

from app.processing import readers
from app.processing.readers import DocumentReadError, file_type_for, read_document, split_pages
from tests.helpers import invoice_text, make_pdf, make_scanned_pdf, render_image


def test_digital_pdf_is_read_without_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(readers, "ocr_image", lambda image: pytest.fail("OCR should not run"))
    result = read_document(make_pdf(tmp_path / "invoice.pdf", [invoice_text()]))

    assert result.page_count == 1
    assert len(result.segments) == 1
    assert "INV-1001" in result.segments[0].text


def test_scanned_pdf_goes_through_ocr(tmp_path):
    result = read_document(make_scanned_pdf(tmp_path / "scan.pdf", [invoice_text()]))

    assert "INV-1001" in result.text
    assert "137.50" in result.text


def test_multi_page_pdf_is_split_per_invoice(tmp_path):
    pages = [invoice_text("INV-1"), "Terms and conditions apply.", invoice_text("INV-2")]
    result = read_document(make_pdf(tmp_path / "batch.pdf", pages))

    assert result.page_count == 3
    assert [s.source for s in result.segments] == ["pages 1-2", "page 3"]


def test_split_pages_keeps_repeated_invoice_number_together():
    segments = split_pages([invoice_text("INV-9"), invoice_text("INV-9"), invoice_text("INV-10")])
    assert [s.source for s in segments] == ["pages 1-2", "page 3"]


def test_poor_quality_image(tmp_path):
    path = tmp_path / "photo.jpg"
    render_image(invoice_text(), degrade=True).save(path, quality=60)

    text = read_document(path).text
    assert "INV-1001" in text
    assert "137.50" in text


def test_multi_page_tiff(tmp_path):
    path = tmp_path / "scan.tiff"
    first, second = render_image(invoice_text("INV-1")), render_image(invoice_text("INV-2"))
    first.save(path, save_all=True, append_images=[second])

    result = read_document(path)
    assert result.page_count == 2
    assert len(result.segments) == 2


@pytest.mark.parametrize("name", ["broken.pdf", "broken.png", "broken.xlsx"])
def test_corrupted_files_raise_read_error(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"this is not a real file \x00\x01\x02")
    with pytest.raises(DocumentReadError):
        read_document(path)


def test_excel_with_register_and_free_form_sheets(tmp_path):
    path = tmp_path / "book.xlsx"
    register = pd.DataFrame(
        {
            "Invoice No": ["INV-1", "INV-2"],
            "Invoice Date": ["2024-01-05", "2024-01-06"],
            "Vendor": ["ACME", "Initech"],
            "Subtotal": ["100.00", "200.00"],
            "VAT": ["10.00", "20.00"],
            "Total": ["110.00", "220.00"],
            "Currency": ["USD", "EUR"],
        }
    )
    notes = pd.DataFrame({"Note": ["Payment run for January"]})
    with pd.ExcelWriter(path) as writer:
        register.to_excel(writer, sheet_name="Register", index=False)
        notes.to_excel(writer, sheet_name="Notes", index=False)

    result = read_document(path)
    structured = [s for s in result.segments if s.data]
    assert result.page_count == 2
    assert [s.data.invoice_number for s in structured] == ["INV-1", "INV-2"]
    assert structured[1].data.total == 220.0
    assert structured[1].data.currency == "EUR"
    assert any(s.data is None and "Payment run" in s.text for s in result.segments)


def test_csv_line_items_are_grouped_by_invoice(tmp_path):
    path = tmp_path / "lines.csv"
    path.write_text(
        "invoice_number,supplier,description,qty,unit_price,amount,total\n"
        "INV-7,ACME,Widget,2,5.00,10.00,15.00\n"
        "INV-7,ACME,Bolt,1,5.00,5.00,15.00\n"
        "INV-8,ACME,Nut,3,1.00,3.00,3.00\n"
    )
    segments = read_document(path).segments

    assert len(segments) == 2
    assert [item.description for item in segments[0].data.line_items] == ["Widget", "Bolt"]
    assert segments[0].data.total == 15.0


def test_unsupported_extension():
    assert file_type_for("malware.exe") is None
    assert file_type_for("INVOICE.PDF") == "pdf"
