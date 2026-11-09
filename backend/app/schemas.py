from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.processing.extraction import LineItem


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EventOut(ORMModel):
    stage: str
    message: str
    created_at: datetime


class InvoiceOut(ORMModel):
    id: str
    document_id: str
    position: int
    source: str | None
    data: dict
    validation_errors: list[dict]
    needs_review: bool
    corrected: bool


class DocumentOut(ORMModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    status: str
    error: str | None
    page_count: int | None
    processing_ms: int | None
    created_at: datetime
    invoice_count: int = 0
    needs_review: bool = False


class DocumentDetail(DocumentOut):
    invoices: list[InvoiceOut]
    events: list[EventOut]


class StatusOut(BaseModel):
    id: str
    status: str
    error: str | None
    last_event: EventOut | None


class InvoiceCorrection(BaseModel):
    """Only the fields that are sent get changed."""

    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None
    line_items: list[LineItem] | None = None


class SearchHit(BaseModel):
    invoice: InvoiceOut
    filename: str
    score: float | None = None
