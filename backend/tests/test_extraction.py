from types import SimpleNamespace

import pytest

from app.config import settings
from app.processing import extraction
from app.processing.extraction import ExtractionError, InvoiceData, extract, extract_with_rules
from tests.helpers import invoice_text


def test_rules_extract_all_labelled_fields():
    data = extract_with_rules(invoice_text())

    assert data.invoice_number == "INV-1001"
    assert data.invoice_date == "2024-03-15"
    assert data.supplier_name == "ACME Supplies Ltd"
    assert data.customer_name == "Globex Corporation"
    assert (data.subtotal, data.tax, data.total) == (125.0, 12.5, 137.5)
    assert data.currency == "USD"
    assert [item.amount for item in data.line_items] == [100.0, 25.0]


def test_rules_leave_missing_fields_empty():
    data = extract_with_rules("Receipt\nThanks for shopping\nTotal 42.00")

    assert data.total == 42.0
    assert data.invoice_number is None
    assert data.invoice_date is None
    assert data.subtotal is None
    assert data.tax is None
    assert data.currency is None


def test_rules_do_not_confuse_subtotal_with_total():
    data = extract_with_rules("Subtotal 90.00\nTotal 99.00")
    assert data.subtotal == 90.0
    assert data.total == 99.0


def fake_client(response):
    parse = lambda **kwargs: response  # noqa: E731
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))


def test_llm_is_used_when_api_key_is_set(monkeypatch):
    expected = InvoiceData(invoice_number="X-1", total=10.0, uncertain_fields=["invoice_date"])
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        extraction, "_client", lambda: fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=expected))
    )

    assert extract("some invoice text") == expected


def test_llm_refusal_raises(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        extraction, "_client", lambda: fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    )

    with pytest.raises(ExtractionError):
        extract("some invoice text")
