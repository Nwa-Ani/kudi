from decimal import Decimal

import pytest

from app.fees import FeeError, later_cashout_notes, receiving_fee


def test_usd_150_international_ng_fee():
    fee = receiving_fee(Decimal("150.00"), "USD")
    # 4.90% of 150 = 7.35, plus $0.30 fixed = $7.65, net $142.35
    assert fee.percent_fee == Decimal("7.35")
    assert fee.fixed_fee == Decimal("0.30")
    assert fee.total_fee == Decimal("7.65")
    assert fee.net_amount == Decimal("142.35")
    assert fee.currency == "USD"
    assert "4.90%" in fee.assumption
    assert "paypal.com/ng/business/paypal-business-fees" in fee.source_url


def test_eur_100_fee():
    fee = receiving_fee(Decimal("100"), "EUR")
    # 4.90% of 100 = 4.90, plus €0.35 = €5.25, net €94.75
    assert fee.percent_fee == Decimal("4.90")
    assert fee.fixed_fee == Decimal("0.35")
    assert fee.total_fee == Decimal("5.25")
    assert fee.net_amount == Decimal("94.75")


def test_gbp_fixed_fee():
    fee = receiving_fee(Decimal("75"), "GBP")
    assert fee.fixed_fee == Decimal("0.20")
    assert fee.percent_fee == Decimal("3.68")  # 4.90% of 75 = 3.675 -> 3.68
    assert fee.total_fee == Decimal("3.88")


def test_rejects_ngn():
    with pytest.raises(FeeError, match="does not settle"):
        receiving_fee(Decimal("400000"), "NGN")


def test_rejects_unknown_currency_instead_of_guessing():
    with pytest.raises(FeeError, match="No official PayPal fixed fee"):
        receiving_fee(Decimal("100"), "KES")


def test_rejects_zero():
    with pytest.raises(FeeError, match="greater than zero"):
        receiving_fee(Decimal("0"), "USD")


def test_later_cashout_notes_use_official_rates():
    notes = later_cashout_notes(Decimal("142.35"), "USD")
    assert notes["conversion_percent_label"] == "3.0%"
    assert notes["conversion_fee"] == "4.27"  # 3% of 142.35 = 4.2705 -> 4.27
    assert notes["after_paypal_conversion"] == "138.08"
    assert notes["partner_withdrawal_percent_label"] == "2.0%"
    assert notes["partner_withdrawal_fixed_usd"] == "1.50"
