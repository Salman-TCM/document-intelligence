# Evaluation results

Generated 2026-11-08 15:21 by `python -m eval.run_eval`.

- Extractor: **rule-based (no API key set)**
- Dataset: 40 files, 58 labelled invoices
- Document success rate: **100.0%** (failure rate 0.0%)
- Corrupted files rejected cleanly: 3/3
- Overall field accuracy: **98.3%**
- Validation caught 100.0% of 4 planted arithmetic errors; false-positive rate on clean invoices 3.7%
- Processing time per document: mean 0.31s, p95 0.84s, total 12.2s

## Accuracy by field

| Field | Accuracy |
|---|---|
| invoice_number | 100.0% |
| invoice_date | 100.0% |
| supplier_name | 100.0% |
| customer_name | 93.1% |
| subtotal | 96.6% |
| tax | 98.3% |
| total | 98.3% |
| currency | 100.0% |
| line_items | 89.7% |

## By document type

| Type | Files | Processed OK | Field accuracy | Mean time |
|---|---|---|---|---|
| digital_pdf | 12 | 12 | 100.0% | 0.00s |
| scanned_pdf | 8 | 8 | 87.5% | 0.75s |
| image | 8 | 8 | 100.0% | 0.53s |
| tiff | 2 | 2 | 100.0% | 0.89s |
| multi_invoice_pdf | 1 | 1 | 100.0% | 0.01s |
| excel | 3 | 3 | 100.0% | 0.04s |
| csv | 3 | 3 | 100.0% | 0.01s |
| corrupted | 3 | 3 | n/a | 0.00s |
