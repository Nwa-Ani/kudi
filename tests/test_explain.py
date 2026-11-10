from decimal import Decimal

from app.explain import build_explanation, money
from app.fees import receiving_fee
from app.fx import FxQuote


def test_money_formats():
    assert money(Decimal("150.00"), "USD") == "$150.00"
    assert money(Decimal("216372"), "NGN") == "₦216,372"
    assert money(Decimal("94.75"), "EUR") == "€94.75"


def test_plain_english_covers_fees_and_naira_disclaimer():
    fee = receiving_fee(Decimal("150"), "USD")
    fx = FxQuote(
        base="USD",
        quote="NGN",
        rate=Decimal("1500"),
        source="test",
        fetched_at_wat="9:00 AM WAT on 10 November 2026",
        rate_time_wat="8:00 AM WAT on 10 November 2026",
        rate_time_utc="2026-11-10T07:00:00+00:00",
    )
    explained = build_explanation(
        client="Sarah",
        items="Logo design",
        due_label="Friday, 13 November 2026",
        fee=fee,
        fx=fx,
    )
    text = explained["plain"]
    assert "Sarah" in text
    assert "$150.00" in text
    assert "4.90%" in text
    assert "$0.30" in text
    assert "$7.65" in text
    assert "$142.35" in text
    assert "does not pay out in Nigerian Naira" in text
    assert "8:00 AM WAT on 10 November 2026" in text
    assert "₦213,525" in text
    assert "3.0%" in text
    assert "—" not in text
    assert "–" not in text
    assert explained["you_receive"] == "$142.35"
    assert explained["naira"]["available"] is True


def test_fx_error_does_not_block_paypal_total():
    fee = receiving_fee(Decimal("150"), "USD")
    explained = build_explanation(
        client=None,
        items=None,
        due_label=None,
        fee=fee,
        fx=None,
        fx_error="offline",
    )
    assert "$142.35" in explained["plain"]
    assert "unavailable" in explained["plain"]
    assert explained["naira"]["available"] is False
