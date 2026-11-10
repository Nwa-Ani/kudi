"""PayPal Orders v2 sandbox checkout, with a mock mode when keys are missing.

Creates a shareable checkout (approve) link. Live/production mode is refused.
Credentials are read from the environment and are never logged or returned.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.fees import PAYPAL_CHECKOUT_CURRENCIES, decimals_for, quantize_amount

SANDBOX_API = "https://api-m.sandbox.paypal.com"
# Live API is intentionally not wired up.


class PayPalError(RuntimeError):
    """Raised when the PayPal sandbox call fails."""


@dataclass(frozen=True)
class CheckoutLink:
    mode: str  # "mock" or "sandbox"
    order_id: str
    status: str
    approve_url: str
    currency: str
    amount: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env(name: str) -> str:
    """Read an env var. If NAME_P0, NAME_P1, ... are set, concatenate those instead.

    Some hosts cap a single environment value at a very short length. Split
    parts let the full sandbox credential be provided without printing it.
    """
    if os.environ.get(f"{name}_P0") is not None:
        parts: list[str] = []
        index = 0
        while f"{name}_P{index}" in os.environ:
            parts.append(os.environ.get(f"{name}_P{index}") or "")
            index += 1
        return "".join(parts).strip()
    return (os.environ.get(name) or "").strip()


def paypal_mode() -> str:
    """Return 'sandbox' when both credentials are present, otherwise 'mock'."""
    env = _env("PAYPAL_ENV").lower() or "sandbox"
    if env in {"live", "production"}:
        raise PayPalError(
            "Live PayPal mode is disabled for this project. Use sandbox credentials only."
        )
    if _env("PAYPAL_CLIENT_ID") and _env("PAYPAL_CLIENT_SECRET"):
        return "sandbox"
    return "mock"


def credentials_present() -> bool:
    return bool(_env("PAYPAL_CLIENT_ID") and _env("PAYPAL_CLIENT_SECRET"))


_token_cache: dict[str, Any] = {"token": None, "expires": 0.0}


def _access_token() -> str:
    cached = _token_cache.get("token")
    if cached and time.time() < float(_token_cache.get("expires") or 0) - 30:
        return str(cached)
    client_id = _env("PAYPAL_CLIENT_ID")
    secret = _env("PAYPAL_CLIENT_SECRET")
    if not client_id or not secret:
        raise PayPalError("PayPal sandbox credentials are not set.")
    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            f"{SANDBOX_API}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, secret),
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 400:
        # Do not include response body if it might echo credentials.
        raise PayPalError(
            f"PayPal could not issue a sandbox access token (HTTP {response.status_code}). "
            "Check that the Client ID and Secret are sandbox credentials."
        )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise PayPalError("PayPal did not return a sandbox access token.")
    expires_in = int(payload.get("expires_in") or 300)
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + expires_in
    return token


def _amount_value(amount: Decimal, currency: str) -> str:
    quantized = quantize_amount(Decimal(amount), currency)
    places = decimals_for(currency)
    return f"{quantized:.{places}f}"


def _mock_checkout(amount: Decimal, currency: str) -> CheckoutLink:
    token = "MOCK-" + secrets.token_hex(8).upper()
    return CheckoutLink(
        mode="mock",
        order_id=token,
        status="CREATED",
        approve_url=f"https://www.sandbox.paypal.com/checkoutnow?token={token}",
        currency=currency,
        amount=_amount_value(amount, currency),
    )


def create_checkout_link(
    amount: Decimal,
    currency: str,
    description: str,
    return_url: str,
    cancel_url: str,
    brand_name: str = "Naira Freelancer Pay",
) -> CheckoutLink:
    code = currency.upper()
    if code not in PAYPAL_CHECKOUT_CURRENCIES:
        raise PayPalError(
            f"{code} is not a PayPal checkout currency this app supports. "
            "Use USD, EUR, GBP, or another currency listed on the official fee page."
        )
    value = _amount_value(amount, code)
    if paypal_mode() == "mock":
        return _mock_checkout(Decimal(value), code)

    description = " ".join((description or "Freelance invoice").split())[:120]
    token = _access_token()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "description": description or "Freelance invoice",
                "amount": {"currency_code": code, "value": value},
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": brand_name[:127],
                    "landing_page": "NO_PREFERENCE",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            }
        },
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            f"{SANDBOX_API}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=body,
        )
    if response.status_code >= 400:
        raise PayPalError(
            f"PayPal sandbox could not create the order (HTTP {response.status_code})."
        )
    payload = response.json()
    order_id = payload.get("id") or ""
    status = payload.get("status") or "CREATED"
    approve = None
    for link in payload.get("links") or []:
        if link.get("rel") in {"approve", "payer-action"}:
            approve = link.get("href")
            break
    if not order_id or not approve:
        raise PayPalError("PayPal sandbox created an order but returned no checkout link.")
    return CheckoutLink(
        mode="sandbox",
        order_id=order_id,
        status=status,
        approve_url=approve,
        currency=code,
        amount=value,
    )



def get_order(order_id: str) -> dict[str, Any]:
    """Load a sandbox order and return only non-secret status fields."""
    order_id = (order_id or "").strip()
    if not order_id:
        raise PayPalError("An order id is required.")
    if paypal_mode() == "mock":
        if not order_id.startswith("MOCK-"):
            raise PayPalError("Mock mode can only read mock order ids.")
        return {
            "order_id": order_id,
            "status": "CREATED",
            "intent": "CAPTURE",
            "mode": "mock",
        }
    token = _access_token()
    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            f"{SANDBOX_API}/v2/checkout/orders/{order_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        raise PayPalError(
            f"PayPal sandbox could not load the order (HTTP {response.status_code})."
        )
    payload = response.json()
    return {
        "order_id": payload.get("id") or order_id,
        "status": payload.get("status") or "",
        "intent": payload.get("intent") or "",
        "mode": "sandbox",
    }
