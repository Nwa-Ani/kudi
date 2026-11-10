"""Real PayPal sandbox order test. Skips when credentials are not set.

This test never prints or asserts on secret values. It only checks that an
order can be created and then read back by id and status.
"""

from decimal import Decimal

import pytest

from app.parser import parse_invoice
from app.paypal import credentials_present, create_checkout_link, get_order, paypal_mode


pytestmark = pytest.mark.skipif(
    not credentials_present(),
    reason="PayPal sandbox credentials are not set",
)


def test_sandbox_parse_create_and_read_order():
    parsed = parse_invoice("Logo design for Sarah, 150 USD, due Friday")
    assert parsed.ok
    assert parsed.amount == "150.00"
    assert parsed.currency == "USD"
    assert paypal_mode() == "sandbox"

    link = create_checkout_link(
        amount=Decimal(parsed.amount),
        currency=parsed.currency,
        description=f"{parsed.items} for {parsed.client}",
        return_url="http://127.0.0.1:8000/done",
        cancel_url="http://127.0.0.1:8000/cancelled",
    )
    assert link.mode == "sandbox"
    assert link.status in {"CREATED", "PAYER_ACTION_REQUIRED", "SAVED"}
    assert link.order_id
    assert not link.order_id.startswith("MOCK-")
    assert link.approve_url.startswith("https://www.sandbox.paypal.com/")
    assert link.amount == "150.00"

    fetched = get_order(link.order_id)
    assert fetched["mode"] == "sandbox"
    assert fetched["order_id"] == link.order_id
    assert fetched["status"] in {"CREATED", "PAYER_ACTION_REQUIRED", "SAVED", "APPROVED"}
    assert fetched["intent"] in {"CAPTURE", ""}
