from decimal import Decimal

import pytest

from app import paypal as paypalmod
from app.paypal import PayPalError, create_checkout_link


def test_mock_checkout_when_keys_missing(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("PAYPAL_ENV", raising=False)
    link = create_checkout_link(
        amount=Decimal("150.00"),
        currency="USD",
        description="Logo design for Sarah",
        return_url="http://localhost/done",
        cancel_url="http://localhost/cancelled",
    )
    assert link.mode == "mock"
    assert link.order_id.startswith("MOCK-")
    assert "checkoutnow?token=MOCK-" in link.approve_url
    assert link.amount == "150.00"
    assert link.currency == "USD"


def test_refuses_live_mode(monkeypatch):
    monkeypatch.setenv("PAYPAL_ENV", "live")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "x")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "y")
    with pytest.raises(PayPalError, match="Live PayPal mode is disabled"):
        paypalmod.paypal_mode()


def test_refuses_unsupported_currency(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    with pytest.raises(PayPalError, match="not a PayPal checkout currency"):
        create_checkout_link(
            amount=Decimal("100"),
            currency="NGN",
            description="test",
            return_url="http://localhost/done",
            cancel_url="http://localhost/cancelled",
        )
