"""HTTP API and static UI for Kudi."""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.explain import attach_fx_for, build_explanation
from app.fees import (
    PAYPAL_CHECKOUT_CURRENCIES,
    FeeError,
    fee_source_meta,
    quantize_amount,
    receiving_fee,
)
from app import fx as fxmod
from app.fx import FxError
from app.envutil import read_env
from app.parser import maybe_refine_with_llm, now_wat, parse_invoice
from app.paypal import PayPalError, credentials_present, create_checkout_link, paypal_mode

load_dotenv()

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(
    title="Kudi",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class TextBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class ConfirmBody(BaseModel):
    text: str | None = None
    client: str | None = None
    items: str | None = None
    amount: str
    currency: str
    due_date: str | None = None
    due_date_label: str | None = None


def _safe_mode() -> str:
    try:
        return paypal_mode()
    except PayPalError:
        return "blocked-live"


def _public_base(request: Request) -> str:
    configured = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def _ngn_to_usd(amount: Decimal) -> tuple[Decimal, object | None, str | None]:
    try:
        quote = fxmod.fetch_rate("USD", "NGN")
    except FxError as exc:
        raise FeeError(
            "This invoice is in Naira, and a mid-market USD rate is unavailable "
            f"right now, so a PayPal link cannot be created. {exc}"
        ) from exc
    # quote.rate is NGN per 1 USD, so USD = NGN / rate
    usd = quantize_amount(amount / quote.rate, "USD")
    if usd <= 0:
        raise FeeError("The Naira amount is too small to convert to a USD checkout.")
    return usd, quote, None


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "mode": _safe_mode(),
        "credentials": "present" if credentials_present() else "absent",
        "timezone": "Africa/Lagos",
    }


@app.get("/api/status")
def status() -> dict:
    return {
        "ok": True,
        "mode": _safe_mode(),
        "credentials": "present" if credentials_present() else "absent",
        "fees": fee_source_meta(),
        "parser": "rule-based, with optional LLM if a key is set",
        "llm_configured": bool(read_env("OPENAI_API_KEY") or read_env("GROQ_API_KEY")),
    }


@app.post("/api/parse")
def api_parse(body: TextBody) -> dict:
    parsed = parse_invoice(body.text)
    parsed = maybe_refine_with_llm(parsed, body.text)
    return {"ok": parsed.ok, "parse": parsed.as_dict()}


def _prepare(body: ConfirmBody, request: Request, create_link: bool) -> dict:
    currency = (body.currency or "").upper().strip()
    try:
        amount = Decimal(str(body.amount).replace(",", "").replace("₦", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return {"ok": False, "error": "The amount could not be read. Use a number such as 150 or 350000."}

    original_amount = amount
    original_currency = currency
    converted_to_usd = False
    fx_for_conversion = None

    if currency == "NGN":
        amount, fx_for_conversion, _ = _ngn_to_usd(amount)
        currency = "USD"
        converted_to_usd = True
    elif currency not in PAYPAL_CHECKOUT_CURRENCIES:
        return {
            "ok": False,
            "error": (
                f"{currency or 'That currency'} is not a PayPal checkout currency "
                "this app can price from the official Nigeria fee page."
            ),
        }

    try:
        fee = receiving_fee(amount, currency)
    except FeeError as exc:
        return {"ok": False, "error": str(exc)}

    fx = fx_for_conversion
    fx_error = None
    if fx is None:
        fx, fx_error = attach_fx_for(currency)

    explanation = build_explanation(
        client=body.client,
        items=body.items,
        due_label=body.due_date_label,
        fee=fee,
        original_amount=original_amount if converted_to_usd else None,
        original_currency=original_currency if converted_to_usd else None,
        fx=fx,
        fx_error=fx_error,
        converted_to_usd=converted_to_usd,
    )

    result: dict = {
        "ok": True,
        "mode": _safe_mode(),
        "invoice": {
            "client": body.client,
            "items": body.items,
            "amount": format(fee.invoice_amount, "f"),
            "currency": fee.currency,
            "due_date": body.due_date,
            "due_date_label": body.due_date_label,
            "original_amount": format(original_amount, "f") if converted_to_usd else None,
            "original_currency": original_currency if converted_to_usd else None,
        },
        "explanation": explanation,
    }

    if not create_link:
        return result

    description_parts = [p for p in [body.items, f"for {body.client}" if body.client else None] if p]
    description = " ".join(description_parts) or "Freelance invoice"
    base = _public_base(request)
    try:
        link = create_checkout_link(
            amount=fee.invoice_amount,
            currency=fee.currency,
            description=description,
            return_url=f"{base}/done",
            cancel_url=f"{base}/cancelled",
        )
    except PayPalError as exc:
        return {"ok": False, "error": str(exc), "explanation": explanation}

    result["checkout"] = link.as_dict()
    return result


@app.post("/api/quote")
def api_quote(body: ConfirmBody, request: Request) -> dict:
    return _prepare(body, request, create_link=False)


@app.post("/api/create-link")
def api_create_link(body: ConfirmBody, request: Request) -> dict:
    return _prepare(body, request, create_link=True)


@app.post("/api/run")
def api_run(body: TextBody, request: Request) -> dict:
    """Parse, quote, and create a link in one step. The UI still lets you edit first."""
    parsed = parse_invoice(body.text)
    parsed = maybe_refine_with_llm(parsed, body.text)
    if not parsed.ok or not parsed.amount or not parsed.currency:
        return {"ok": False, "parse": parsed.as_dict(), "error": "I need an amount and a currency first."}
    prepared = _prepare(
        ConfirmBody(
            text=body.text,
            client=parsed.client,
            items=parsed.items,
            amount=parsed.amount,
            currency=parsed.currency,
            due_date=parsed.due_date,
            due_date_label=parsed.due_date_label,
        ),
        request,
        create_link=True,
    )
    prepared["parse"] = parsed.as_dict()
    return prepared


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/done")
@app.get("/cancelled")
def flow_pages() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.exception_handler(FeeError)
async def fee_error_handler(_request: Request, exc: FeeError) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.exception_handler(PayPalError)
async def paypal_error_handler(_request: Request, exc: PayPalError) -> JSONResponse:
    status = 503 if "Live PayPal" in str(exc) else 400
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=status)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
