"""Official PayPal receiving fees for a Nigerian (NG) merchant account.

Source (retrieved 10 November 2026):
  https://www.paypal.com/ng/business/paypal-business-fees
  Last updated on that page: 28 October 2026

Nigeria is listed in the "Receiving international transactions" table in the
group AO, BF, BH, BJ, CD, CI, CM, DZ, ET, FJ, GA, GN, JO, KG, MG, NA, NC, NG,
OM, PF, PW, RW, SA, SL, TG, TJ, TM, TN, TZ, UG, ZM, and ZW. The rate for that
group, for buyers in all markets, is 4.90% + a fixed fee based on the currency
received.

Fixed fees are taken from "Fixed fee for commercial transactions (based on
currency received)" on the same page.

PayPal does not settle a Nigerian merchant account in NGN. NGN is not in the
commercial receiving fixed-fee table, so Naira invoices are converted to a
PayPal-supported currency (USD by default) before a checkout link is created.

Currency conversion (same page, "Converting balance, transfers, and payments
received into another currency", Middle East & Africa, including Nigeria):
3.0% above the base exchange rate.

Withdrawals through a third-party partner (same page, Nigeria is listed):
2.0% + 1.50 USD, plus whatever the partner charges.

This module does not invent percentages. If a currency has no official fixed
fee in the table above, fee calculation is refused for that currency.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

FEE_SOURCE_URL = "https://www.paypal.com/ng/business/paypal-business-fees"
FEE_SOURCE_UPDATED = "28 October 2026"
FEE_SOURCE_RETRIEVED = "10 November 2026"

# International commercial receiving rate for an NG seller.
INTERNATIONAL_PERCENT = Decimal("0.049")

# Official fixed fees, commercial transactions, currency received.
FIXED_FEES: dict[str, Decimal] = {
    "AUD": Decimal("0.30"),
    "BRL": Decimal("0.60"),
    "CAD": Decimal("0.30"),
    "CZK": Decimal("10.00"),
    "DKK": Decimal("2.60"),
    "EUR": Decimal("0.35"),
    "HKD": Decimal("2.35"),
    "HUF": Decimal("90.00"),
    "ILS": Decimal("1.20"),
    "JPY": Decimal("40.00"),
    "MYR": Decimal("2.00"),
    "MXN": Decimal("4.00"),
    "TWD": Decimal("10.00"),
    "NZD": Decimal("0.45"),
    "NOK": Decimal("2.80"),
    "PHP": Decimal("15.00"),
    "PLN": Decimal("1.35"),
    "RUB": Decimal("10.00"),
    "SGD": Decimal("0.50"),
    "SEK": Decimal("3.25"),
    "CHF": Decimal("0.55"),
    "THB": Decimal("11.00"),
    "GBP": Decimal("0.20"),
    "USD": Decimal("0.30"),
}

# PayPal amount decimal places (minor units).
CURRENCY_DECIMALS: dict[str, int] = {
    "JPY": 0,
    "HUF": 0,
    "TWD": 0,
}

# Official extra fees that may apply later, not part of the receiving fee.
PAYPAL_CONVERSION_PERCENT = Decimal("0.030")  # NG, converting received funds
PARTNER_WITHDRAWAL_PERCENT = Decimal("0.020")  # NG, third-party partner
PARTNER_WITHDRAWAL_FIXED_USD = Decimal("1.50")

# Currencies PayPal checkout commonly accepts. NGN is not among them.
PAYPAL_CHECKOUT_CURRENCIES = frozenset(FIXED_FEES.keys())


class FeeError(ValueError):
    """Raised when an official fee cannot be applied."""


def decimals_for(currency: str) -> int:
    return CURRENCY_DECIMALS.get(currency.upper(), 2)


def quantize_amount(amount: Decimal, currency: str) -> Decimal:
    places = decimals_for(currency)
    step = Decimal("1") if places == 0 else Decimal("0.1") ** places
    return Decimal(amount).quantize(step, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ReceivingFee:
    currency: str
    invoice_amount: Decimal
    percent_rate: Decimal
    percent_fee: Decimal
    fixed_fee: Decimal
    total_fee: Decimal
    net_amount: Decimal
    assumption: str
    source_url: str
    source_updated: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = format(value, "f")
        data["percent_rate_label"] = f"{(self.percent_rate * 100):.2f}%"
        return data


def receiving_fee(amount: Decimal, currency: str) -> ReceivingFee:
    """Fee a Nigerian account pays to receive an international commercial payment."""
    code = (currency or "").upper().strip()
    if code == "NGN":
        raise FeeError(
            "PayPal does not settle Nigerian merchant payments in NGN, so a "
            "receiving fee cannot be calculated in Naira. Convert the invoice "
            "to a PayPal-supported currency such as USD first."
        )
    if code not in FIXED_FEES:
        raise FeeError(
            f"No official PayPal fixed fee for {code or 'an unknown currency'} "
            f"is listed on the Nigeria seller fee page, so this app will not "
            f"guess a percentage or a fixed fee."
        )
    invoice = quantize_amount(Decimal(amount), code)
    if invoice <= 0:
        raise FeeError("The invoice amount must be greater than zero.")
    percent_fee = quantize_amount(invoice * INTERNATIONAL_PERCENT, code)
    fixed_fee = quantize_amount(FIXED_FEES[code], code)
    total_fee = quantize_amount(percent_fee + fixed_fee, code)
    net = quantize_amount(invoice - total_fee, code)
    if net <= 0:
        raise FeeError(
            "The official PayPal receiving fee would be larger than this "
            "invoice amount, so a payment link was not created."
        )
    return ReceivingFee(
        currency=code,
        invoice_amount=invoice,
        percent_rate=INTERNATIONAL_PERCENT,
        percent_fee=percent_fee,
        fixed_fee=fixed_fee,
        total_fee=total_fee,
        net_amount=net,
        assumption=(
            "Assumes a Nigerian PayPal account receiving an international "
            "commercial payment (a client in a different country). The official "
            "rate is 4.90% plus a fixed fee in the currency received."
        ),
        source_url=FEE_SOURCE_URL,
        source_updated=FEE_SOURCE_UPDATED,
    )


def later_cashout_notes(net_amount: Decimal, currency: str) -> dict[str, Any]:
    """Official extra fees that may apply if the freelancer later converts or withdraws.

    These are shown separately. They are not deducted from the PayPal receiving total.
    """
    code = currency.upper()
    conversion_fee = quantize_amount(net_amount * PAYPAL_CONVERSION_PERCENT, code)
    after_conversion = quantize_amount(net_amount - conversion_fee, code)
    return {
        "conversion_percent_label": "3.0%",
        "conversion_fee": format(conversion_fee, "f"),
        "after_paypal_conversion": format(after_conversion, "f"),
        "conversion_applies_when": (
            "If PayPal later converts this balance into another currency "
            "(including when withdrawing), the official extra fee for a "
            "Nigerian account is 3.0% above the base exchange rate."
        ),
        "partner_withdrawal": (
            "If you withdraw through a PayPal third-party partner in Nigeria, "
            "the official PayPal fee is 2.0% plus 1.50 USD, and the partner "
            "may charge more. This app does not guess the partner's fee."
        ),
        "partner_withdrawal_percent_label": "2.0%",
        "partner_withdrawal_fixed_usd": "1.50",
        "source_url": FEE_SOURCE_URL,
        "source_updated": FEE_SOURCE_UPDATED,
    }


def fee_source_meta() -> dict[str, str]:
    return {
        "url": FEE_SOURCE_URL,
        "updated": FEE_SOURCE_UPDATED,
        "retrieved": FEE_SOURCE_RETRIEVED,
        "international_percent": "4.90%",
        "seller_market": "Nigeria (NG)",
    }
