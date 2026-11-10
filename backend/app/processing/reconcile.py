"""Cross-checks invoices between two documents, e.g. a PDF batch against an Excel register."""

COMPARED_FIELDS = ["invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]


def _key(invoice_number: str | None) -> str | None:
    return invoice_number.strip().upper().replace(" ", "") if invoice_number else None


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.02
    return str(a).strip().lower() == str(b).strip().lower()


def reconcile(left: list[dict], right: list[dict]) -> dict:
    """Match invoices by number and report field differences.

    `left` and `right` are lists of extracted invoice data (InvoiceData as dicts).
    """
    left_by_key = {_key(inv.get("invoice_number")): inv for inv in left if inv.get("invoice_number")}
    right_by_key = {_key(inv.get("invoice_number")): inv for inv in right if inv.get("invoice_number")}

    matched = []
    for key in left_by_key.keys() & right_by_key.keys():
        a, b = left_by_key[key], right_by_key[key]
        differences = [
            {"field": field, "left": a.get(field), "right": b.get(field)}
            for field in COMPARED_FIELDS
            if not _same(a.get(field), b.get(field))
        ]
        matched.append({"invoice_number": a["invoice_number"], "differences": differences})

    return {
        "matched": sorted(matched, key=lambda m: m["invoice_number"]),
        "only_in_left": sorted(left_by_key[k]["invoice_number"] for k in left_by_key.keys() - right_by_key.keys()),
        "only_in_right": sorted(right_by_key[k]["invoice_number"] for k in right_by_key.keys() - left_by_key.keys()),
    }
