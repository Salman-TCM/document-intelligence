# Document Intelligence

Upload invoices as PDF, scans, photos, Excel or CSV. The system pulls out the invoice
fields, checks the numbers add up, flags anything that needs a human, and makes
everything searchable.

- **Backend:** FastAPI, RQ workers on Redis, PostgreSQL with pgvector
- **Processing:** PyMuPDF for PDFs, Tesseract for OCR, pandas/openpyxl/xlrd for spreadsheets
- **Extraction:** Claude with structured output, plus a rule-based fallback that works offline
- **Frontend:** React + Vite, served by nginx

Docs:
- [Architecture, database schema and design decisions](docs/architecture.md)
- [Evaluation report with measured metrics](docs/evaluation.md)
- [Test results](docs/test-results.txt)
- [AI prompts and AI-assisted development](docs/ai-usage.md)

## Running it

You need Docker with Compose.

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY to use Claude; leave it empty for the rule-based extractor
docker compose up --build
```

- UI: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

To try it with sample files, generate the evaluation set and upload a few of them
from `backend/eval/data`:

```bash
docker compose run --rm -v ./backend:/app api python -m eval.generate_dataset
```

### Running without Docker

You need Python 3.12, Node 20, Tesseract, PostgreSQL with the pgvector extension,
and Redis.

```bash
cd backend
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/docintel
uvicorn app.main:app --reload            # API
rq worker documents                      # worker, in a second terminal

cd frontend
npm install
npm run dev                              # http://localhost:5173, proxies /api to :8000
```

## Tests and evaluation

```bash
docker compose run --rm api pytest -v       # 36 tests, uses a separate test database

# The eval scripts write to backend/eval, so mount the source folder.
docker compose run --rm -v ./backend:/app api python -m eval.generate_dataset
docker compose run --rm -v ./backend:/app api python -m eval.run_eval
docker compose run --rm -v ./backend:/app api python -m eval.benchmark   # 1000-page digital + 100-page scanned PDF
```

The tests cover PDF text extraction, OCR on scanned PDFs, degraded photos and
multi-page TIFFs, Excel and CSV parsing, corrupted files, rule-based and (mocked) LLM
extraction, every validation rule, reconciliation, and the API end to end: upload,
status, corrections, duplicates, keyword and semantic search, reprocessing a failed
job, upload limits and API key checks.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/documents` | Upload one or more files (`files` form field). Returns right away; processing happens in the background. |
| GET | `/api/documents` | List documents with status, invoice count and review flag. `?status=failed` filters. |
| GET | `/api/documents/{id}` | Document with its extracted invoices, validation errors and processing history. |
| GET | `/api/documents/{id}/status` | Status, error and latest event only. Cheap to poll. |
| GET | `/api/documents/{id}/file` | Download the original file. |
| POST | `/api/documents/{id}/reprocess` | Queue a failed (or finished) document again. |
| PATCH | `/api/invoices/{id}` | Correct fields by hand. Validation runs again and the change is logged. |
| GET | `/api/search` | `q` with `mode=keyword` (full-text) or `mode=semantic` (vector). Filters: `supplier`, `needs_review`, `date_from`, `date_to`, `min_total`, `max_total`. |
| GET | `/api/reconcile?left=&right=` | Compare invoices between two documents, e.g. a PDF batch against the Excel register. |

Example:

```bash
curl -F files=@invoice.pdf -F files=@register.xlsx http://localhost:8000/api/documents
curl "http://localhost:8000/api/search?q=office%20furniture&mode=semantic"
curl -X PATCH http://localhost:8000/api/invoices/<id> -H 'Content-Type: application/json' -d '{"total": 137.5}'
```

If `API_KEY` is set, send it as an `X-API-Key` header (and set `VITE_API_KEY` when
building the frontend).

## Extracted fields

```json
{
  "invoice_number": "INV-1001",
  "invoice_date": "2024-03-15",
  "supplier_name": "ACME Supplies Ltd",
  "customer_name": "Globex Corporation",
  "subtotal": 125.0,
  "tax": 12.5,
  "total": 137.5,
  "currency": "USD",
  "line_items": [{"description": "Widget A", "quantity": 2, "unit_price": 50.0, "amount": 100.0}],
  "uncertain_fields": []
}
```

A field that isn't in the document is `null`; it is never guessed. Fields the model
couldn't read clearly are listed in `uncertain_fields` and show up as validation
issues.

## Validation rules

An invoice is flagged for review when any of these is true:

- a required field is missing (number, date, supplier, total, currency)
- an amount is negative, or the date is invalid or in the future
- quantity x unit price doesn't equal the line amount
- line items don't add up to the subtotal
- subtotal + tax doesn't equal the total (2-cent tolerance)
- another invoice has the same number from the same supplier
- the extractor marked a field as uncertain

## Configuration

Set these in `.env`:

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables Claude extraction. Empty means rule-based. |
| `LLM_MODEL` | `claude-opus-5-5` | |
| `API_KEY` | empty | Require `X-API-Key` on all `/api` routes. |
| `MAX_UPLOAD_MB` | 200 | Per file. |
| `OCR_WORKERS` | 4 | OCR threads per worker. |

## Project layout

```
backend/
  app/
    main.py              API routes
    worker.py            background job: read, extract, validate, embed, save
    models.py            SQLAlchemy tables
    invoices.py          saving extracted data and the duplicate check
    processing/
      readers.py         PDF / image / spreadsheet reading, splitting into invoices
      ocr.py             image cleanup and Tesseract
      extraction.py      Claude and rule-based extractors
      validation.py      business rules
      reconcile.py       cross-document comparison
      embeddings.py      local embeddings for semantic search
  tests/
  eval/                  dataset generator, evaluation and benchmark scripts
frontend/src/
  components/            documents, invoice editor, search, reconcile
docs/
```
