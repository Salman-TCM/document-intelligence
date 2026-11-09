"""Local sentence embeddings for semantic search.

bge-small runs on CPU through ONNX, so semantic search works without another
API key. Swap the model here if you need multilingual support; keep
EMBEDDING_DIM in models.py in sync.
"""

from functools import lru_cache

from app.processing.extraction import InvoiceData

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME)


def embed(text: str) -> list[float]:
    return next(iter(_model().embed([text]))).tolist()


def invoice_search_text(data: InvoiceData, raw_text: str) -> str:
    """What we embed: the key fields first, then the start of the raw text."""
    items = ", ".join(item.description for item in data.line_items if item.description)
    summary = (
        f"Invoice {data.invoice_number or ''} from {data.supplier_name or 'unknown supplier'} "
        f"to {data.customer_name or 'unknown customer'}. Items: {items}."
    )
    return f"{summary}\n{raw_text[:1500]}"
