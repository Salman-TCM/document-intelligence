from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice
from app.processing.extraction import InvoiceData
from app.processing.validation import validate


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def find_duplicate(session: Session, invoice: Invoice) -> str | None:
    """Another invoice with the same number from the same supplier, if any."""
    if not invoice.invoice_number:
        return None
    query = select(Invoice.id).where(
        func.upper(Invoice.invoice_number) == invoice.invoice_number.upper(),
        Invoice.id != invoice.id,
    )
    if invoice.supplier_name:
        query = query.where(func.lower(Invoice.supplier_name) == invoice.supplier_name.lower())
    return session.scalar(query.limit(1))


def save_invoice_data(session: Session, invoice: Invoice, data: InvoiceData) -> None:
    """Store extracted (or corrected) data on the invoice and re-run validation."""
    invoice.data = data.model_dump()
    invoice.invoice_number = data.invoice_number
    invoice.supplier_name = data.supplier_name
    invoice.invoice_date = _parse_date(data.invoice_date)
    invoice.total = data.total

    session.add(invoice)
    session.flush()  # assigns invoice.id so the duplicate check can exclude it

    invoice.validation_errors = validate(data, duplicate_of=find_duplicate(session, invoice))
    invoice.needs_review = bool(invoice.validation_errors)
