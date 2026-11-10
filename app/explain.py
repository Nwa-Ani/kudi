"""Plain-English payment explanation. No em dashes in user-facing text."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.fees import ReceivingFee, later_cashout_notes, quantize_amount
from app import fx as fxmod
from app.fx import FxError, FxQuote, convert


def money(amount: Decimal | str, currency: str) -> str:
    value = Decimal(str(amount))
    code = currency.upper()
    if code == "NGN":
        whole = quantize_amount(value, "JPY")  # 0 decimals
        return f"₦{whole:,.0f}"
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$"}
    symbol = symbols.get(code)
    places = 0 if code in {"JPY", "HUF", "TWD"} else 2
    formatted = f"{value:,.{places}f}"
    if symbol:
        return f"{symbol}{formatted}"
    return f"{formatted} {code}"


def build_explanation(
    *,
    client: str | None,
    items: str | None,
    due_label: str | None,
    fee: ReceivingFee,
    original_amount: Decimal | None = None,
    original_currency: str | None = None,
    fx: FxQuote | None = None,
    fx_error: str | None = None,
    converted_to_usd: bool = False,
) -> dict[str, Any]:
    client_name = client or "your client"
    work = items or "the work on this invoice"
    pay_line = (
        f"{client_name if client else 'Your client'} is asked to pay "
        f"{money(fee.invoice_amount, fee.currency)} for {work}"
    )
    if due_label:
        pay_line += f", due {due_label}"
    pay_line += "."
    if pay_line[0].islower():
        pay_line = pay_line[0].upper() + pay_line[1:]

    convert_note = ""
    if converted_to_usd and original_amount is not None and original_currency:
        convert_note = (
            f" The invoice was written as {money(original_amount, original_currency)}. "
            "PayPal does not settle in Nigerian Naira, so the checkout link is in "
            f"US dollars at the mid-market rate of 1 {fx.base if fx else 'USD'} = "
            f"{(fx.rate if fx else '')} {fx.quote if fx else 'NGN'}"
            + (f" as of {fx.rate_time_wat}." if fx else ".")
        )
        # The above could be awkward if fx is missing. Rewritten below if needed.

    fee_line = (
        "PayPal's fee for a Nigerian account receiving an international payment "
        f"is 4.90% plus a {money(fee.fixed_fee, fee.currency)} fixed fee. "
        f"On this invoice, that is {money(fee.total_fee, fee.currency)}. "
        f"You would receive {money(fee.net_amount, fee.currency)} in your PayPal account."
    )

    naira_line = (
        "PayPal does not pay out in Nigerian Naira. The Naira figures below are a "
        "mid-market guide, not a guaranteed bank credit."
    )
    naira: dict[str, Any] = {"available": False}
    if fx is not None:
        net_ngn = convert(fee.net_amount, fx.rate, "NGN") if fx.quote == "NGN" else None
        invoice_ngn = convert(fee.invoice_amount, fx.rate, "NGN") if fx.quote == "NGN" else None
        # If the quote is USD per NGN somehow, skip. We always request BASE->NGN.
        if fx.quote == "NGN":
            cashout = later_cashout_notes(fee.net_amount, fee.currency)
            after_conv = Decimal(cashout["after_paypal_conversion"])
            after_conv_ngn = convert(after_conv, fx.rate, "NGN")
            naira = {
                "available": True,
                "invoice_ngn": money(invoice_ngn, "NGN"),
                "net_ngn": money(net_ngn, "NGN"),
                "rate": format(fx.rate, "f"),
                "rate_label": f"1 {fx.base} = {fx.rate:,.4f} NGN",
                "rate_time_wat": fx.rate_time_wat,
                "source": fx.source,
                "after_paypal_conversion_ngn": money(after_conv_ngn, "NGN"),
            }
            naira_line = (
                f"PayPal does not pay out in Nigerian Naira. At the mid-market rate of "
                f"1 {fx.base} = {fx.rate:,.2f} NGN as of {fx.rate_time_wat}, "
                f"{money(fee.net_amount, fee.currency)} is about {money(net_ngn, 'NGN')}. "
                "That figure is only a guide. Your bank or PayPal's own conversion, if you "
                "convert later, will be different. If PayPal later converts this balance, "
                f"the official extra fee for a Nigerian account is 3.0%, which would leave "
                f"about {money(after_conv, fee.currency)} "
                f"(about {money(after_conv_ngn, 'NGN')} at the same mid-market rate). "
                "Withdrawals through a PayPal partner in Nigeria can also add 2.0% plus "
                "1.50 USD, plus the partner's own charges."
            )
    elif fx_error:
        naira_line = (
            "PayPal does not pay out in Nigerian Naira. A mid-market Naira estimate "
            f"is unavailable right now ({fx_error}). The PayPal total above is still valid."
        )

    if converted_to_usd:
        if fx and original_amount is not None and original_currency:
            convert_note = (
                f"The invoice was written as {money(original_amount, original_currency)}. "
                "PayPal does not settle in Nigerian Naira, so the checkout link uses "
                f"{money(fee.invoice_amount, fee.currency)} at the mid-market rate of "
                f"1 {fx.base} = {fx.rate:,.2f} NGN as of {fx.rate_time_wat}."
            )
        elif original_amount is not None and original_currency:
            convert_note = (
                f"The invoice was written as {money(original_amount, original_currency)}. "
                "PayPal does not settle in Nigerian Naira, so the checkout link was "
                "created in US dollars."
            )

    paragraphs = [pay_line]
    if convert_note:
        paragraphs.append(convert_note)
    paragraphs.extend([fee_line, naira_line])
    plain = " ".join(paragraphs)

    cashout = later_cashout_notes(fee.net_amount, fee.currency)
    return {
        "plain": plain,
        "paragraphs": paragraphs,
        "client_pays": money(fee.invoice_amount, fee.currency),
        "paypal_fee": money(fee.total_fee, fee.currency),
        "you_receive": money(fee.net_amount, fee.currency),
        "naira": naira,
        "cashout": cashout,
        "fee": fee.as_dict(),
        "fx": fx.as_dict() if fx else None,
        "fx_error": fx_error,
        "converted_to_usd": converted_to_usd,
        "source_url": fee.source_url,
        "source_updated": fee.source_updated,
    }


def attach_fx_for(currency: str, amount_for_ngn_rate: str | None = None) -> tuple[FxQuote | None, str | None]:
    """Fetch BASE->NGN. amount_for_ngn_rate is unused and kept for call-site clarity."""
    del amount_for_ngn_rate
    try:
        return fxmod.fetch_rate(currency, "NGN"), None
    except FxError as exc:
        return None, str(exc)
