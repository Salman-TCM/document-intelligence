"""Generates a labelled evaluation set of invoices in every supported format.

    python -m eval.generate_dataset --out eval/data

Each file comes with ground truth in labels.json. A few invoices contain a
deliberate arithmetic error so we can also measure whether validation catches it.
"""

import argparse
import json
import random
from pathlib import Path

import fitz
import pandas as pd

from tests.helpers import render_image

SUPPLIERS = ["ACME Supplies Ltd", "Northwind Traders", "Initech LLC", "Umbrella Logistics", "Stark Components"]
CUSTOMERS = ["Globex Corporation", "Wayne Enterprises", "Hooli Inc", "Soylent Foods", "Cyberdyne Systems"]
ITEMS = [
    "Steel bolts",
    "Office chairs",
    "Cloud hosting",
    "Consulting hours",
    "Printer toner",
    "Shipping",
    "Laptop stand",
    "Software licence",
    "Cleaning service",
    "Copper wire",
]
CURRENCIES = {"USD": "$", "EUR": "€", "GBP": "£"}
DATE_FORMATS = ["%Y-%m-%d", "%d %B %Y", "%B %d, %Y"]


def make_invoice(rng: random.Random, number: int, with_error: bool = False) -> dict:
    items = []
    for description in rng.sample(ITEMS, rng.randint(1, 4)):
        quantity = rng.randint(1, 20)
        unit_price = round(rng.uniform(5, 400), 2)
        items.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": round(quantity * unit_price, 2),
            }
        )
    subtotal = round(sum(i["amount"] for i in items), 2)
    tax = round(subtotal * rng.choice([0, 0.05, 0.1, 0.2]), 2)
    total = round(subtotal + tax + (rng.choice([-10, 25]) if with_error else 0), 2)
    return {
        "invoice_number": f"INV-{number:05d}",
        "invoice_date": f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "supplier_name": rng.choice(SUPPLIERS),
        "customer_name": rng.choice(CUSTOMERS),
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": rng.choice(list(CURRENCIES)),
        "line_items": items,
        "has_error": with_error,
    }


def invoice_text(inv: dict, rng: random.Random) -> str:
    """Render an invoice with one of a few layouts, like documents from different suppliers."""
    date = pd.Timestamp(inv["invoice_date"]).strftime(rng.choice(DATE_FORMATS))
    symbol = CURRENCIES[inv["currency"]]
    lines = [
        f"{item['description']:<22}{item['quantity']:>5}   {item['unit_price']:>10.2f}   {item['amount']:>10.2f}"
        for item in inv["line_items"]
    ]
    number_label = rng.choice(["Invoice No:", "Invoice #", "Invoice Number:"])
    supplier_label = rng.choice(["From:", "Vendor:", "Supplier:"])
    return "\n".join(
        [
            f"{supplier_label} {inv['supplier_name']}",
            "123 Business Road, Springfield",
            "",
            "INVOICE",
            f"{number_label} {inv['invoice_number']}",
            f"Date: {date}",
            f"Bill To: {inv['customer_name']}",
            "",
            f"{'Description':<22}{'Qty':>5}   {'Unit Price':>10}   {'Amount':>10}",
            *lines,
            "",
            f"Subtotal {symbol}{inv['subtotal']:,.2f}",
            f"Tax {symbol}{inv['tax']:,.2f}",
            f"Total {inv['currency']} {symbol}{inv['total']:,.2f}",
        ]
    )


def write_pdf(path: Path, pages: list[str]) -> None:
    with fitz.open() as pdf:
        for text in pages:
            pdf.new_page().insert_text((50, 72), text, fontname="cour", fontsize=10)
        pdf.save(path)


def write_scanned_pdf(path: Path, pages: list[str], degrade: bool) -> None:
    with fitz.open() as pdf:
        for text in pages:
            png = path.with_suffix(".tmp.png")
            render_image(text, degrade=degrade).save(png)
            page = pdf.new_page()
            page.insert_image(page.rect, filename=str(png))
            png.unlink()
        pdf.save(path)


def register_rows(invoices: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Invoice No": i["invoice_number"],
                "Invoice Date": i["invoice_date"],
                "Supplier": i["supplier_name"],
                "Customer": i["customer_name"],
                "Subtotal": i["subtotal"],
                "Tax": i["tax"],
                "Total": i["total"],
                "Currency": i["currency"],
            }
            for i in invoices
        ]
    )


def line_item_rows(invoices: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "invoice_number": i["invoice_number"],
                "date": i["invoice_date"],
                "vendor": i["supplier_name"],
                "customer": i["customer_name"],
                "description": item["description"],
                "qty": item["quantity"],
                "unit_price": item["unit_price"],
                "amount": item["amount"],
                "subtotal": i["subtotal"],
                "tax": i["tax"],
                "total": i["total"],
                "currency": i["currency"],
            }
            for i in invoices
            for item in i["line_items"]
        ]
    )


def generate(out: Path, seed: int = 7) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    counter = iter(range(1, 100_000))
    labels = []

    def invoices(n: int, error_rate: float = 0.15) -> list[dict]:
        return [make_invoice(rng, next(counter), with_error=rng.random() < error_rate) for _ in range(n)]

    def add(name: str, file_invoices: list[dict], kind: str, expect_failure: bool = False) -> None:
        labels.append({"file": name, "kind": kind, "expect_failure": expect_failure, "invoices": file_invoices})

    for n in range(12):
        [inv] = invoices(1)
        write_pdf(out / f"digital_{n}.pdf", [invoice_text(inv, rng)])
        add(f"digital_{n}.pdf", [inv], "digital_pdf")

    for n in range(8):
        [inv] = invoices(1)
        write_scanned_pdf(out / f"scanned_{n}.pdf", [invoice_text(inv, rng)], degrade=n % 2 == 1)
        add(f"scanned_{n}.pdf", [inv], "scanned_pdf")

    for n in range(8):
        [inv] = invoices(1)
        name = f"photo_{n}.{'jpg' if n % 2 else 'png'}"
        render_image(invoice_text(inv, rng), degrade=n % 2 == 1).save(out / name)
        add(name, [inv], "image")

    for n in range(2):
        batch = invoices(2)
        first, *rest = [render_image(invoice_text(inv, rng)) for inv in batch]
        first.save(out / f"multipage_{n}.tiff", save_all=True, append_images=rest)
        add(f"multipage_{n}.tiff", batch, "tiff")

    batch = invoices(5)
    pages = []
    for inv in batch:
        pages += [invoice_text(inv, rng), "Payment terms: 30 days. Thank you for your business."]
    write_pdf(out / "batch_10_pages.pdf", pages)
    add("batch_10_pages.pdf", batch, "multi_invoice_pdf")

    for n in range(3):
        batch = invoices(4)
        register_rows(batch).to_excel(out / f"register_{n}.xlsx", index=False)
        # A register has no line items, so none are expected back.
        add(f"register_{n}.xlsx", [{**inv, "line_items": []} for inv in batch], "excel")

    for n in range(3):
        batch = invoices(3)
        line_item_rows(batch).to_csv(out / f"lines_{n}.csv", index=False)
        add(f"lines_{n}.csv", batch, "csv")

    for name in ["corrupted.pdf", "corrupted.png", "corrupted.xlsx"]:
        (out / name).write_bytes(bytes(rng.randrange(256) for _ in range(2048)))
        add(name, [], "corrupted", expect_failure=True)

    (out / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"Wrote {len(labels)} files to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("eval/data"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    generate(args.out, args.seed)
