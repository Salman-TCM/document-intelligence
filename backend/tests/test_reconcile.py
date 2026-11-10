from app.processing.reconcile import reconcile


def test_reconcile_reports_differences_and_unmatched():
    pdf = [
        {"invoice_number": "INV-1", "total": 100.0, "supplier_name": "ACME"},
        {"invoice_number": "INV-2", "total": 50.0, "supplier_name": "ACME"},
        {"invoice_number": "INV-3", "total": 10.0},
    ]
    excel = [
        {"invoice_number": "inv-1", "total": 100.001, "supplier_name": "acme"},
        {"invoice_number": "INV-2", "total": 55.0, "supplier_name": "ACME"},
        {"invoice_number": "INV-4", "total": 20.0},
    ]

    result = reconcile(pdf, excel)

    assert result["matched"] == [
        {"invoice_number": "INV-1", "differences": []},
        {"invoice_number": "INV-2", "differences": [{"field": "total", "left": 50.0, "right": 55.0}]},
    ]
    assert result["only_in_left"] == ["INV-3"]
    assert result["only_in_right"] == ["INV-4"]
