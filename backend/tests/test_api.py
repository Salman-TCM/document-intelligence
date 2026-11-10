"""End-to-end API tests. Jobs run inline, so an upload is fully processed when the request returns."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.main import app
from tests.helpers import invoice_text, make_pdf

REGISTER_CSV = (
    "Invoice No,Invoice Date,Supplier,Subtotal,Tax,Total,Currency\n"
    "INV-1001,2024-03-15,ACME Supplies Ltd,125.00,12.50,137.50,USD\n"
    "INV-2002,2024-03-16,ACME Supplies Ltd,80.00,8.00,88.00,USD\n"
)


@pytest.fixture
def client(test_database):
    with TestClient(app) as client:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE documents CASCADE"))
        yield client


def upload(client, *paths: Path):
    files = [("files", (path.name, path.read_bytes())) for path in paths]
    response = client.post("/api/documents", files=files)
    assert response.status_code == 201, response.text
    return [client.get(f"/api/documents/{doc['id']}").json() for doc in response.json()]


def test_upload_pdf_and_inspect_results(client, tmp_path):
    [doc] = upload(client, make_pdf(tmp_path / "invoice.pdf", [invoice_text()]))

    assert doc["status"] == "done"
    assert doc["invoice_count"] == 1
    invoice = doc["invoices"][0]
    assert invoice["data"]["invoice_number"] == "INV-1001"
    assert invoice["data"]["total"] == 137.5
    assert invoice["needs_review"] is False
    assert [e["stage"] for e in doc["events"]] == ["uploaded", "started", "read", "done"]

    status = client.get(f"/api/documents/{doc['id']}/status").json()
    assert status["status"] == "done"
    assert client.get("/api/documents").json()[0]["invoice_count"] == 1


def test_unsupported_file_type_is_rejected(client):
    response = client.post("/api/documents", files=[("files", ("run.exe", b"MZ"))])
    assert response.status_code == 400


def test_oversized_upload_is_rejected(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    response = client.post("/api/documents", files=[("files", ("big.csv", b"a,b\n1,2\n"))])
    assert response.status_code == 413


def test_api_key_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_corrupted_file_fails_and_can_be_reprocessed(client, tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 truncated")
    [doc] = upload(client, broken)
    assert doc["status"] == "failed"
    assert "Could not open PDF" in doc["error"]

    # Simulate fixing the stored file (e.g. a re-sync from the source system), then retry.
    stored = Path(settings.upload_dir) / f"{doc['id']}.pdf"
    make_pdf(stored, [invoice_text()])
    response = client.post(f"/api/documents/{doc['id']}/reprocess")
    assert response.status_code == 202

    doc = client.get(f"/api/documents/{doc['id']}").json()
    assert doc["status"] == "done"
    assert doc["error"] is None


def test_validation_errors_and_manual_correction(client, tmp_path):
    [doc] = upload(client, make_pdf(tmp_path / "bad.pdf", [invoice_text(total="150.00")]))
    invoice = doc["invoices"][0]
    assert invoice["needs_review"] is True
    assert [e["code"] for e in invoice["validation_errors"]] == ["total_mismatch"]

    response = client.patch(f"/api/invoices/{invoice['id']}", json={"total": 137.5})
    assert response.status_code == 200
    corrected = response.json()
    assert corrected["needs_review"] is False
    assert corrected["corrected"] is True
    assert corrected["data"]["total"] == 137.5


def test_duplicate_invoice_is_flagged(client, tmp_path):
    path = make_pdf(tmp_path / "invoice.pdf", [invoice_text()])
    first, second = upload(client, path, path)

    assert first["invoices"][0]["needs_review"] is False
    assert [e["code"] for e in second["invoices"][0]["validation_errors"]] == ["duplicate"]


def test_keyword_and_semantic_search(client, tmp_path):
    widgets = invoice_text("INV-1")
    consulting = invoice_text("INV-2").replace("Widget A", "Legal consulting").replace("Service fee", "Court filing")
    upload(client, make_pdf(tmp_path / "a.pdf", [widgets]), make_pdf(tmp_path / "b.pdf", [consulting]))

    hits = client.get("/api/search", params={"q": "consulting"}).json()
    assert [h["invoice"]["data"]["invoice_number"] for h in hits] == ["INV-2"]

    hits = client.get("/api/search", params={"q": "INV-1", "mode": "keyword"}).json()
    assert hits[0]["invoice"]["data"]["invoice_number"] == "INV-1"

    hits = client.get("/api/search", params={"q": "lawyer services", "mode": "semantic"}).json()
    assert hits[0]["invoice"]["data"]["invoice_number"] == "INV-2"

    hits = client.get("/api/search", params={"min_total": 1000}).json()
    assert hits == []


def test_reconcile_pdf_against_excel_register(client, tmp_path):
    register = tmp_path / "register.csv"
    register.write_text(REGISTER_CSV)
    pdf, csv = upload(client, make_pdf(tmp_path / "invoice.pdf", [invoice_text()]), register)

    result = client.get("/api/reconcile", params={"left": pdf["id"], "right": csv["id"]}).json()

    assert result["matched"][0]["invoice_number"] == "INV-1001"
    # The register has no customer column, so that is the only difference.
    assert [d["field"] for d in result["matched"][0]["differences"]] == ["customer_name"]
    assert result["only_in_right"] == ["INV-2002"]
