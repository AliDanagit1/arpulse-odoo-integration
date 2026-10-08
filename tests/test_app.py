import os
os.environ["MOCK_ODOO"] = "true"
from fastapi.testclient import TestClient
from app.main import app
from app.service import bucket_of, convert_amount

c = TestClient(app)


def test_buckets():
    assert [bucket_of(d) for d in (0, 1, 30, 31, 60, 61, 90, 91)] == ["current", "1-30", "1-30", "31-60", "31-60", "61-90", "61-90", "90+"]
    assert convert_amount(10000, "USD", "LBP", 89500) == 895000000


def test_dashboard_and_invoices():
    d = c.get("/api/dashboard").json()
    assert d["open_count"] == 40 and sum(a["count"] for a in d["aging"]) == 40
    assert d["currency"] == "LBP" and d["mixed_currency"] is False
    assert c.get("/api/invoices?bucket=90%2B").json()["total"] > 0


def test_reminder_and_duplicate_guard():
    assert c.post("/api/invoices/1/reminder", json={"template": "firm"}).status_code == 200
    assert c.post("/api/invoices/1/reminder", json={}).status_code == 429
    assert c.post("/api/invoices/9999/reminder", json={}).status_code == 409
