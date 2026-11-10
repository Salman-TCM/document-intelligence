import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session, init_db
from app.invoices import save_invoice_data
from app.models import SEARCH_CONFIG, Document, Invoice, invoice_text_vector, new_id
from app.processing.embeddings import embed, invoice_search_text
from app.processing.extraction import InvoiceData
from app.processing.readers import FILE_TYPES, file_type_for
from app.schemas import DocumentDetail, DocumentOut, InvoiceCorrection, InvoiceOut, SearchHit, StatusOut
from app.worker import enqueue, log_event

UPLOAD_DIR = Path(settings.upload_dir)
CHUNK_SIZE = 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if settings.api_key and not secrets.compare_digest(x_api_key or "", settings.api_key):
        raise HTTPException(401, "Invalid or missing API key")


app = FastAPI(title="Document Intelligence API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/api/health")
def health():
    return {"status": "ok"}


def get_document(session: Session, document_id: str) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


def _save_upload(upload: UploadFile, destination: Path) -> tuple[int, str]:
    """Stream the upload to disk, enforcing the size limit. Returns (size, sha256)."""
    limit = settings.max_upload_mb * 1024 * 1024
    digest, size = hashlib.sha256(), 0
    with destination.open("wb") as out:
        while chunk := upload.file.read(CHUNK_SIZE):
            size += len(chunk)
            if size > limit:
                out.close()
                destination.unlink()
                raise HTTPException(413, f"{upload.filename} is larger than {settings.max_upload_mb} MB")
            digest.update(chunk)
            out.write(chunk)
    return size, digest.hexdigest()


# --- Documents -------------------------------------------------------------


@api.post("/documents", status_code=201)
def upload_documents(files: list[UploadFile], session: SessionDep) -> list[DocumentOut]:
    for upload in files:
        if file_type_for(upload.filename or "") is None:
            allowed = ", ".join(sorted(FILE_TYPES))
            raise HTTPException(400, f"Unsupported file type: {upload.filename}. Allowed: {allowed}")

    documents = []
    for upload in files:
        filename = Path(upload.filename).name
        document_id = new_id()
        # Files are stored under a generated name; the user's filename is never used as a path.
        path = UPLOAD_DIR / f"{document_id}{Path(filename).suffix.lower()}"
        size, sha256 = _save_upload(upload, path)
        document = Document(
            id=document_id,
            filename=filename[:255],
            file_type=file_type_for(filename),
            size_bytes=size,
            sha256=sha256,
            storage_path=str(path),
        )
        session.add(document)
        log_event(session, document, "uploaded")
        documents.append(document)
    session.commit()

    for document in documents:
        enqueue(document.id)
    return documents


@api.get("/documents")
def list_documents(
    session: SessionDep,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> list[DocumentOut]:
    counts = (
        select(
            Invoice.document_id,
            func.count().label("invoice_count"),
            func.bool_or(Invoice.needs_review).label("needs_review"),
        )
        .group_by(Invoice.document_id)
        .subquery()
    )
    query = (
        select(Document, counts.c.invoice_count, counts.c.needs_review)
        .outerjoin(counts, counts.c.document_id == Document.id)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(Document.status == status)

    return [
        DocumentOut.model_validate(document).model_copy(
            update={"invoice_count": invoice_count or 0, "needs_review": bool(needs_review)}
        )
        for document, invoice_count, needs_review in session.execute(query)
    ]


@api.get("/documents/{document_id}")
def get_document_detail(document_id: str, session: SessionDep) -> DocumentDetail:
    document = get_document(session, document_id)
    return DocumentDetail.model_validate(document).model_copy(
        update={
            "invoice_count": len(document.invoices),
            "needs_review": any(invoice.needs_review for invoice in document.invoices),
        }
    )


@api.get("/documents/{document_id}/status")
def get_status(document_id: str, session: SessionDep) -> StatusOut:
    document = get_document(session, document_id)
    return StatusOut(
        id=document.id,
        status=document.status,
        error=document.error,
        last_event=document.events[-1] if document.events else None,
    )


@api.get("/documents/{document_id}/file")
def download_file(document_id: str, session: SessionDep):
    document = get_document(session, document_id)
    return FileResponse(document.storage_path, filename=document.filename)


@api.post("/documents/{document_id}/reprocess", status_code=202)
def reprocess_document(document_id: str, session: SessionDep) -> DocumentOut:
    document = get_document(session, document_id)
    if document.status in ("queued", "processing"):
        raise HTTPException(409, f"Document is already {document.status}")
    document.status = "queued"
    log_event(session, document, "requeued")
    session.commit()
    enqueue(document.id)
    return document


# --- Invoices --------------------------------------------------------------


@api.patch("/invoices/{invoice_id}")
def correct_invoice(invoice_id: str, correction: InvoiceCorrection, session: SessionDep) -> InvoiceOut:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    changes = correction.model_dump(exclude_unset=True, mode="json")
    if not changes:
        raise HTTPException(400, "No fields to update")

    data = InvoiceData(**{**invoice.data, **changes})
    data.uncertain_fields = [field for field in data.uncertain_fields if field not in changes]
    save_invoice_data(session, invoice, data)
    invoice.corrected = True
    invoice.embedding = embed(invoice_search_text(data, invoice.text))
    log_event(session, invoice.document, "corrected", f"Invoice {invoice.position + 1}: changed {', '.join(changes)}")
    session.commit()
    return invoice


@api.get("/search")
def search_invoices(
    session: SessionDep,
    q: str = "",
    mode: Literal["keyword", "semantic"] = "keyword",
    supplier: str | None = None,
    needs_review: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
    limit: int = Query(20, le=100),
) -> list[SearchHit]:
    query = select(Invoice, Document.filename).join(Document)

    if supplier:
        query = query.where(Invoice.supplier_name.ilike(f"%{supplier}%"))
    if needs_review is not None:
        query = query.where(Invoice.needs_review == needs_review)
    if date_from:
        query = query.where(Invoice.invoice_date >= date_from)
    if date_to:
        query = query.where(Invoice.invoice_date <= date_to)
    if min_total is not None:
        query = query.where(Invoice.total >= min_total)
    if max_total is not None:
        query = query.where(Invoice.total <= max_total)

    q = q.strip()
    if q and mode == "semantic":
        similarity = 1 - Invoice.embedding.cosine_distance(embed(q))
        query = query.add_columns(similarity).where(Invoice.embedding.is_not(None)).order_by(similarity.desc())
    elif q:
        terms = func.websearch_to_tsquery(SEARCH_CONFIG, q)
        rank = func.ts_rank(invoice_text_vector, terms)
        query = (
            query.add_columns(rank)
            .where(or_(invoice_text_vector.op("@@")(terms), Invoice.invoice_number.ilike(f"%{q}%")))
            .order_by(rank.desc())
        )
    else:
        query = query.add_columns(literal(None)).order_by(Invoice.created_at.desc())

    return [
        SearchHit(invoice=InvoiceOut.model_validate(invoice), filename=filename, score=score)
        for invoice, filename, score in session.execute(query.limit(limit))
    ]


app.include_router(api)
