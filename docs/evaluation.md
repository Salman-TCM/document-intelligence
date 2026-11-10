# Evaluation

All numbers here were measured by running the scripts below on the pipeline code in
this repo. Full output: [`backend/eval/report.md`](../backend/eval/report.md) and
`report.json`.

```bash
docker compose run --rm -v ./backend:/app api python -m eval.generate_dataset   # eval/data + labels.json
docker compose run --rm -v ./backend:/app api python -m eval.run_eval           # accuracy, success, timing
docker compose run --rm -v ./backend:/app api python -m eval.benchmark          # large-PDF throughput
```

## Dataset

40 files with 58 labelled invoices, generated with a fixed seed:

| Type | Files | Notes |
|---|---|---|
| Digital PDF | 12 | three label styles, three date formats, USD/EUR/GBP |
| Scanned PDF | 8 | page images only; half of them degraded (skew, blur, noise, low resolution) |
| JPG/PNG | 8 | half degraded, JPEG at default quality |
| Multi-page TIFF | 2 | two invoices each |
| Multi-invoice PDF | 1 | 5 invoices with continuation pages in between (10 pages) |
| Excel register | 3 | one invoice per row |
| CSV | 3 | one line item per row, grouped by invoice number |
| Corrupted | 3 | random bytes named .pdf / .png / .xlsx |

About 15% of the invoices have a deliberate error in the total, to check that
validation catches it.

## Results (rule-based extractor, no API key)

| Metric | Result |
|---|---|
| Document success rate | 100% (37/37 valid files) |
| Failure rate | 0% |
| Corrupted files rejected with a clear error | 3/3 |
| Field accuracy, 8 header fields | 98.3% |
| Line items fully correct | 89.7% |
| Planted total errors flagged | 4/4 |
| Clean invoices wrongly flagged | 3.7% (all caused by OCR misreads on degraded scans) |
| Mean / p95 time per document | 0.31s / 0.84s |

By type: digital PDF, images, TIFF, multi-invoice PDF, Excel and CSV all scored
100% on header fields; scanned PDFs scored 87.5%. The misses were all on the
degraded scans, where Tesseract lost the "Bill To" line or a subtotal.

Field accuracy compares each field to the label: text is compared without case or
whitespace differences, amounts within 0.01, dates as exact ISO strings. A missing
value counts as wrong.

## Large files

| File | Pages | Invoices | Total time | Pages/s |
|---|---|---|---|---|
| Digital PDF | 1000 | 1000 | 0.6s | ~1700 |
| Scanned PDF, 4 OCR threads | 100 | 100 | 36.2s | 2.8 |

So a 1000-page scanned batch takes about 6 minutes on one worker (12-core machine).
Workers scale horizontally, and each one can use more OCR threads (`OCR_WORKERS`).

## Things I tuned using these numbers

- Tesseract `--psm 4` instead of the default. The default split the right-hand
  amount column into a separate block, which dropped line-item accuracy to 25%
  on OCR'd files. `--psm 4` got it to 70% without hurting header fields
  (`--psm 6` was better on line items but much worse on skewed scans).
- Median filter before upscaling, and no autocontrast: autocontrast made the
  degraded images unreadable.
- Amounts are parsed without a leading minus, because OCR often reads `$` as `-`.

## Limitations, honestly

- The dataset is synthetic, and the rule-based extractor was written knowing
  roughly what labels invoices use. Real supplier invoices vary much more (no
  labels, multi-column headers, logos), and the rule-based numbers will be lower
  on them. That's why Claude is the main extractor and the rules are only the
  offline fallback.
- I could not run the LLM path for this report because no Anthropic API key was
  available. To measure it, set `ANTHROPIC_API_KEY` and run `eval.run_eval`
  again; the report header shows which extractor ran.
- `.xls` (legacy Excel) is supported through `xlrd`, but there is no test file for
  it, since current tools can't write the old format.
- Duplicate detection needs the database, so it is covered by the API tests, not
  by this script.
