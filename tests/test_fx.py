from decimal import Decimal

import pytest

from app import fx as fxmod
from app.fx import FxError, convert, fetch_rate


class DummyResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, routes):
        self.routes = routes

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        for prefix, payload in self.routes:
            if url.startswith(prefix) or prefix in url:
                return DummyResponse(payload)
        return DummyResponse({}, status=404)


def test_convert_to_naira_rounds_to_whole_naira():
    assert convert(Decimal("142.35"), Decimal("1500.00"), "NGN") == Decimal("213525")


def test_primary_fx_source(monkeypatch):
    fxmod.clear_cache()
    payload = {
        "result": "success",
        "rates": {"NGN": 1520.25},
        "time_last_update_utc": "Tue, 10 Nov 2026 07:00:00 +0000",
    }
    monkeypatch.setattr(
        fxmod.httpx,
        "Client",
        lambda timeout, follow_redirects: DummyClient([("open.er-api.com", payload)]),
    )
    quote = fetch_rate("USD", "NGN")
    assert quote.source == "open.er-api.com"
    assert quote.rate == Decimal("1520.25")
    assert "WAT" in quote.rate_time_wat
    assert "10 November 2026" in quote.rate_time_wat


def test_fallback_when_primary_fails(monkeypatch):
    fxmod.clear_cache()

    class Flaky(DummyClient):
        def get(self, url):
            if "open.er-api.com" in url:
                raise RuntimeError("down")
            return super().get(url)

    monkeypatch.setattr(
        fxmod.httpx,
        "Client",
        lambda timeout, follow_redirects: Flaky(
            [("api.frankfurter.app", {"date": "2026-11-10", "rates": {"NGN": 1510}})]
        ),
    )
    quote = fetch_rate("USD", "NGN")
    assert quote.source == "api.frankfurter.app"
    assert quote.rate == Decimal("1510")


def test_fx_error_when_both_fail(monkeypatch):
    fxmod.clear_cache()

    class Dead:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise RuntimeError("offline")

    monkeypatch.setattr(fxmod.httpx, "Client", lambda timeout, follow_redirects: Dead())
    with pytest.raises(FxError, match="No mid-market rate"):
        fetch_rate("USD", "NGN")
