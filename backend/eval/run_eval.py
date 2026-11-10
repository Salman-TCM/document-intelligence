"""Runs the processing pipeline over a labelled dataset and reports measured metrics.

    python -m eval.run_eval --data eval/data --report eval/report.md

The extractor is whichever one the app would use: the LLM when ANTHROPIC_API_KEY
is set, otherwise the rule-based fallback. The report says which one ran.
"""

import argparse
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.processing.extraction import extract
from app.processing.readers import read_document
from app.processing.validation import validate

FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]


def same(expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and abs(expected - actual) < 0.01
    return str(expected).strip().lower() == str(actual).strip().lower()


def line_items_match(expected: list[dict], actual: list[dict]) -> bool:
    if len(expected) != len(actual):
        return False
    return all(
        same(e["amount"], a.get("amount")) and same(e["quantity"], a.get("quantity")) for e, a in zip(expected, actual)
    )


def process(path: Path) -> list[dict]:
    result = read_document(path)
    invoices = []
    for segment in result.segments:
        data = segment.data or extract(segment.text)
        invoices.append({**data.model_dump(), "issues": validate(data)})
    return invoices


def evaluate(data_dir: Path) -> dict:
    labels = json.loads((data_dir / "labels.json").read_text())
    field_hits, field_total = defaultdict(int), defaultdict(int)
    by_kind = defaultdict(lambda: {"docs": 0, "ok": 0, "fields_right": 0, "fields_total": 0, "seconds": []})
    planted_errors = flagged_errors = clean = false_flags = 0
    timings, failures = [], []

    for label in labels:
        kind = by_kind[label["kind"]]
        kind["docs"] += 1
        started = time.perf_counter()
        try:
            predicted = process(data_dir / label["file"])
            error = None
        except Exception as exc:
            predicted, error = [], f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        timings.append(elapsed)
        kind["seconds"].append(elapsed)

        if label["expect_failure"]:
            # A corrupted file "succeeds" when it is rejected cleanly with an error.
            kind["ok"] += error is not None
            continue
        if error:
            failures.append({"file": label["file"], "error": error})
            continue
        kind["ok"] += 1

        for i, truth in enumerate(label["invoices"]):
            guess = predicted[i] if i < len(predicted) else {}
            for field in FIELDS:
                hit = same(truth[field], guess.get(field))
                field_hits[field] += hit
                field_total[field] += 1
                kind["fields_right"] += hit
                kind["fields_total"] += 1
            field_hits["line_items"] += line_items_match(truth["line_items"], guess.get("line_items", []))
            field_total["line_items"] += 1

            flagged = any(issue["code"].endswith("mismatch") for issue in guess.get("issues", []))
            if truth["has_error"]:
                planted_errors += 1
                flagged_errors += flagged
            else:
                clean += 1
                false_flags += flagged

    real_docs = [label for label in labels if not label["expect_failure"]]
    total_fields = sum(field_total[f] for f in FIELDS)
    return {
        "extractor": f"LLM ({settings.llm_model})" if settings.anthropic_api_key else "rule-based (no API key set)",
        "documents": len(labels),
        "invoices": sum(len(label["invoices"]) for label in labels),
        "success_rate": (len(real_docs) - len(failures)) / len(real_docs),
        "failure_rate": len(failures) / len(real_docs),
        "corrupted_rejected": by_kind["corrupted"]["ok"],
        "corrupted_total": by_kind["corrupted"]["docs"],
        "field_accuracy": sum(field_hits[f] for f in FIELDS) / total_fields,
        "per_field": {f: field_hits[f] / field_total[f] for f in [*FIELDS, "line_items"]},
        "per_kind": {
            name: {
                "documents": k["docs"],
                "processed_ok": k["ok"],
                "field_accuracy": k["fields_right"] / k["fields_total"] if k["fields_total"] else None,
                "mean_seconds": statistics.mean(k["seconds"]),
            }
            for name, k in by_kind.items()
        },
        "validation_recall": flagged_errors / planted_errors if planted_errors else None,
        "validation_false_positive_rate": false_flags / clean if clean else None,
        "planted_errors": planted_errors,
        "mean_seconds_per_document": statistics.mean(timings),
        "p95_seconds_per_document": statistics.quantiles(timings, n=20)[-1],
        "total_seconds": sum(timings),
        "failures": failures,
    }


def pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def to_markdown(r: dict) -> str:
    lines = [
        "# Evaluation results",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m eval.run_eval`.",
        "",
        f"- Extractor: **{r['extractor']}**",
        f"- Dataset: {r['documents']} files, {r['invoices']} labelled invoices",
        f"- Document success rate: **{pct(r['success_rate'])}** (failure rate {pct(r['failure_rate'])})",
        f"- Corrupted files rejected cleanly: {r['corrupted_rejected']}/{r['corrupted_total']}",
        f"- Overall field accuracy: **{pct(r['field_accuracy'])}**",
        f"- Validation caught {pct(r['validation_recall'])} of {r['planted_errors']} planted arithmetic errors; "
        f"false-positive rate on clean invoices {pct(r['validation_false_positive_rate'])}",
        f"- Processing time per document: mean {r['mean_seconds_per_document']:.2f}s, "
        f"p95 {r['p95_seconds_per_document']:.2f}s, total {r['total_seconds']:.1f}s",
        "",
        "## Accuracy by field",
        "",
        "| Field | Accuracy |",
        "|---|---|",
        *[f"| {field} | {pct(value)} |" for field, value in r["per_field"].items()],
        "",
        "## By document type",
        "",
        "| Type | Files | Processed OK | Field accuracy | Mean time |",
        "|---|---|---|---|---|",
        *[
            f"| {name} | {k['documents']} | {k['processed_ok']} | {pct(k['field_accuracy'])} "
            f"| {k['mean_seconds']:.2f}s |"
            for name, k in r["per_kind"].items()
        ],
    ]
    if r["failures"]:
        lines += ["", "## Unexpected failures", "", *[f"- `{f['file']}`: {f['error']}" for f in r["failures"]]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("eval/data"))
    parser.add_argument("--report", type=Path, default=Path("eval/report.md"))
    args = parser.parse_args()

    results = evaluate(args.data)
    args.report.write_text(to_markdown(results))
    args.report.with_suffix(".json").write_text(json.dumps(results, indent=2))
    print(to_markdown(results))
