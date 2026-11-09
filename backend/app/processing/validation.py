from datetime import date

from app.processing.extraction import InvoiceData

REQUIRED_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "total", "currency"]
AMOUNT_FIELDS = ["subtotal", "tax", "total"]

# Allow a cent or two of rounding difference between printed figures.
TOLERANCE = 0.02


def _issue(code: str, field: str, message: str) -> dict:
    return {"code": code, "field": field, "message": message}


def _differs(a: float, b: float) -> bool:
    return abs(a - b) > TOLERANCE


def validate(data: InvoiceData, duplicate_of: str | None = None) -> list[dict]:
    """Return a list of problems; an empty list means the invoice looks consistent."""
    issues = []

    for field in REQUIRED_FIELDS:
        if getattr(data, field) in (None, ""):
            issues.append(_issue("missing", field, f"{field} is missing"))

    for field in AMOUNT_FIELDS:
        value = getattr(data, field)
        if value is not None and value < 0:
            issues.append(_issue("negative_amount", field, f"{field} is negative ({value})"))

    if data.invoice_date:
        try:
            if date.fromisoformat(data.invoice_date) > date.today():
                issues.append(_issue("future_date", "invoice_date", "invoice date is in the future"))
        except ValueError:
            issues.append(_issue("invalid_date", "invoice_date", f"'{data.invoice_date}' is not a valid date"))

    for i, item in enumerate(data.line_items, start=1):
        if None not in (item.quantity, item.unit_price, item.amount):
            expected = round(item.quantity * item.unit_price, 2)
            if _differs(expected, item.amount):
                issues.append(
                    _issue(
                        "line_item_mismatch",
                        "line_items",
                        f"line {i}: {item.quantity} x {item.unit_price} = {expected}, but amount is {item.amount}",
                    )
                )

    line_amounts = [item.amount for item in data.line_items if item.amount is not None]
    if line_amounts and data.subtotal is not None:
        line_sum = round(sum(line_amounts), 2)
        if _differs(line_sum, data.subtotal):
            issues.append(
                _issue(
                    "subtotal_mismatch", "subtotal", f"line items add up to {line_sum}, but subtotal is {data.subtotal}"
                )
            )

    if data.total is not None:
        if data.subtotal is not None:
            expected = round(data.subtotal + (data.tax or 0), 2)
            if _differs(expected, data.total):
                issues.append(
                    _issue("total_mismatch", "total", f"subtotal + tax = {expected}, but total is {data.total}")
                )
        elif line_amounts and data.tax is None and _differs(sum(line_amounts), data.total):
            issues.append(
                _issue(
                    "total_mismatch",
                    "total",
                    f"line items add up to {round(sum(line_amounts), 2)}, but total is {data.total}",
                )
            )

    for field in data.uncertain_fields:
        issues.append(_issue("uncertain", field, f"{field} could not be read with confidence"))

    if duplicate_of:
        issues.append(
            _issue(
                "duplicate",
                "invoice_number",
                f"invoice {data.invoice_number} from this supplier already exists (invoice {duplicate_of})",
            )
        )

    return issues
