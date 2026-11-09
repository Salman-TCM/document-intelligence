from app.processing.extraction import InvoiceData, LineItem
from app.processing.validation import validate


def valid_invoice(**overrides) -> InvoiceData:
    fields = dict(
        invoice_number="INV-1",
        invoice_date="2024-03-15",
        supplier_name="ACME",
        customer_name="Globex",
        subtotal=125.0,
        tax=12.5,
        total=137.5,
        currency="USD",
        line_items=[
            LineItem(description="Widget", quantity=2, unit_price=50, amount=100),
            LineItem(description="Fee", quantity=1, unit_price=25, amount=25),
        ],
    )
    return InvoiceData(**{**fields, **overrides})


def codes(issues):
    return sorted(issue["code"] for issue in issues)


def test_consistent_invoice_has_no_issues():
    assert validate(valid_invoice()) == []


def test_missing_required_fields():
    issues = validate(valid_invoice(invoice_number=None, currency=None))
    assert {issue["field"] for issue in issues} == {"invoice_number", "currency"}


def test_total_does_not_match_subtotal_plus_tax():
    assert codes(validate(valid_invoice(total=140.0))) == ["total_mismatch"]


def test_rounding_within_tolerance_is_accepted():
    assert validate(valid_invoice(total=137.51)) == []


def test_line_items_do_not_add_up_to_subtotal():
    assert codes(validate(valid_invoice(subtotal=120.0, total=132.5))) == ["subtotal_mismatch"]


def test_line_item_quantity_times_price():
    items = [LineItem(description="Widget", quantity=2, unit_price=50, amount=90)]
    issues = validate(valid_invoice(line_items=items, subtotal=90.0, total=102.5))
    assert codes(issues) == ["line_item_mismatch"]


def test_negative_amount_and_bad_dates():
    assert "negative_amount" in codes(validate(valid_invoice(tax=-1.0)))
    assert codes(validate(valid_invoice(invoice_date="2024-13-45"))) == ["invalid_date"]
    assert codes(validate(valid_invoice(invoice_date="2999-01-01"))) == ["future_date"]


def test_total_checked_against_line_items_when_no_subtotal():
    issues = validate(valid_invoice(subtotal=None, tax=None, total=150.0))
    assert codes(issues) == ["total_mismatch"]


def test_uncertain_and_duplicate_are_flagged():
    issues = validate(valid_invoice(uncertain_fields=["supplier_name"]), duplicate_of="abc123")
    assert codes(issues) == ["duplicate", "uncertain"]
