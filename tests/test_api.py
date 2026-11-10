from decimal import Decimal

from fastapi.testclient import TestClient

from app import fx as fxmod
from app.fx import FxQuote
from app.server import app

client = TestClient(app)


def test_health_and_status(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["ok"] is True
    assert body["mode"] == "mock"
    assert body["credentials"] == "absent"
    status = client.get("/api/status")
    assert status.json()["fees"]["international_percent"] == "4.90%"
    assert "paypal.com/ng/business/paypal-business-fees" in status.json()["fees"]["url"]


def test_index_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Naira Freelancer Pay Agent" in response.text
    assert "—" not in response.text


def test_parse_endpoint():
    response = client.post(
        "/api/parse",
        json={"text": "Logo design for Sarah, 150 USD, due Friday"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["parse"]["client"] == "Sarah"
    assert body["parse"]["amount"] == "150.00"


def test_create_link_mock(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)

    quote = FxQuote(
        base="USD",
        quote="NGN",
        rate=Decimal("1500"),
        source="test",
        fetched_at_wat="9:00 AM WAT on 10 November 2026",
        rate_time_wat="8:00 AM WAT on 10 November 2026",
        rate_time_utc="2026-11-10T07:00:00+00:00",
    )
    monkeypatch.setattr(fxmod, "fetch_rate", lambda *args, **kwargs: quote)

    response = client.post(
        "/api/create-link",
        json={
            "client": "Sarah",
            "items": "Logo design",
            "amount": "150",
            "currency": "USD",
            "due_date": "2026-11-13",
            "due_date_label": "Friday, 13 November 2026",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["mode"] == "mock"
    assert body["checkout"]["order_id"].startswith("MOCK-")
    assert body["explanation"]["you_receive"] == "$142.35"
    assert "does not pay out in Nigerian Naira" in body["explanation"]["plain"]
    assert "—" not in body["explanation"]["plain"]


def test_naira_invoice_converts_to_usd(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    quote = FxQuote(
        base="USD",
        quote="NGN",
        rate=Decimal("1500"),
        source="test",
        fetched_at_wat="9:00 AM WAT on 10 November 2026",
        rate_time_wat="8:00 AM WAT on 10 November 2026",
        rate_time_utc="2026-11-10T07:00:00+00:00",
    )
    monkeypatch.setattr(fxmod, "fetch_rate", lambda *args, **kwargs: quote)
    response = client.post(
        "/api/quote",
        json={"client": "Chidi", "items": "Website", "amount": "450000", "currency": "NGN"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["invoice"]["currency"] == "USD"
    assert body["invoice"]["amount"] == "300.00"  # 450000 / 1500
    assert body["invoice"]["original_currency"] == "NGN"
    assert body["explanation"]["converted_to_usd"] is True
