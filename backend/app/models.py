import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Index, String, Text, func, literal_column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIM = 384


def new_id() -> str:
    return uuid.uuid4().hex


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))  # pdf | image | spreadsheet
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    text: Mapped[str | None] = mapped_column(Text)
    processing_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Invoice.position"
    )
    events: Mapped[list["ProcessingEvent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ProcessingEvent.id"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    source: Mapped[str | None] = mapped_column(String(64))  # e.g. "pages 3-4" or "sheet Invoices"
    text: Mapped[str] = mapped_column(Text, default="")

    data: Mapped[dict] = mapped_column(JSON)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    needs_review: Mapped[bool] = mapped_column(default=False, index=True)
    corrected: Mapped[bool] = mapped_column(default=False)

    # Copies of a few fields from `data` so they can be filtered and indexed.
    invoice_number: Mapped[str | None] = mapped_column(String(64), index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    invoice_date: Mapped[date | None]
    total: Mapped[float | None]

    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="invoices")


# The text search config is inlined (not a bound parameter) so queries match the index expression.
SEARCH_CONFIG = literal_column("'english'")
invoice_text_vector = func.to_tsvector(SEARCH_CONFIG, Invoice.text)
Index("ix_invoices_fts", invoice_text_vector, postgresql_using="gin")


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="events")
