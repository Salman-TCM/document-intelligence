"""Background processing of uploaded documents.

Run a worker with:  rq worker documents --url $REDIS_URL
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from redis import Redis
from rq import Queue

from app.config import settings
from app.db import SessionLocal
from app.invoices import save_invoice_data
from app.models import Document, Invoice, ProcessingEvent
from app.processing.embeddings import embed, invoice_search_text
from app.processing.extraction import ExtractionError, extract
from app.processing.readers import DocumentReadError, Segment, read_document

logger = logging.getLogger(__name__)

LLM_CONCURRENCY = 4
JOB_TIMEOUT = "3h"  # large scanned PDFs can take a while to OCR


def enqueue(document_id: str) -> None:
    if settings.run_jobs_inline:
        process_document(document_id)
        return
    queue = Queue("documents", connection=Redis.from_url(settings.redis_url))
    queue.enqueue(process_document, document_id, job_timeout=JOB_TIMEOUT)


def log_event(session, document: Document, stage: str, message: str = "") -> None:
    session.add(ProcessingEvent(document_id=document.id, stage=stage, message=message))


def _extract(segment: Segment):
    return segment.data or extract(segment.text)


def process_document(document_id: str) -> None:
    started = time.perf_counter()
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        if document is None:
            logger.warning("Document %s no longer exists", document_id)
            return

        document.status = "processing"
        document.error = None
        log_event(session, document, "started")
        session.commit()

        try:
            result = read_document(document.storage_path)
            document.page_count = result.page_count
            document.text = result.text
            log_event(
                session, document, "read", f"{result.page_count} page(s), {len(result.segments)} invoice(s) found"
            )
            session.commit()

            with ThreadPoolExecutor(LLM_CONCURRENCY) as pool:
                extracted = list(pool.map(_extract, result.segments))

            document.invoices.clear()  # reprocessing replaces earlier results
            session.flush()
            for position, (segment, data) in enumerate(zip(result.segments, extracted)):
                invoice = Invoice(document=document, position=position, source=segment.source, text=segment.text)
                save_invoice_data(session, invoice, data)
                invoice.embedding = embed(invoice_search_text(data, segment.text))

            flagged = sum(invoice.needs_review for invoice in document.invoices)
            document.status = "done"
            log_event(
                session, document, "done", f"{len(document.invoices)} invoice(s) extracted, {flagged} need review"
            )
        except Exception as exc:
            if isinstance(exc, (DocumentReadError, ExtractionError)):
                logger.warning("Processing %s failed: %s (%s)", document_id, exc, exc.__cause__)
                error = str(exc)
            else:
                logger.exception("Processing %s failed", document_id)
                error = f"Unexpected error: {type(exc).__name__}: {exc}"
            session.rollback()
            document.status = "failed"
            document.error = error
            log_event(session, document, "failed", error)

        document.processing_ms = int((time.perf_counter() - started) * 1000)
        session.commit()
