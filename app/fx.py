"""Mid-market FX rates with a free primary API and a fallback.

Primary:  https://open.er-api.com/v6/latest/{base}
Fallback: https://api.frankfurter.app/latest?from={base}

Rates are cached in memory for 30 minutes. Timestamps are reported in
Africa/Lagos (WAT). This is a mid-market estimate, not PayPal's conversion rate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import httpx

WAT = ZoneInfo("Africa/Lagos")
CACHE_SECONDS = 30 * 60

PRIMARY_URL = "https://open.er-api.com/v6/latest/{base}"
FALLBACK_URL = "https://api.frankfurter.app/latest?from={base}"

_cache: dict[str, tuple[float, "FxQuote"]] = {}


class FxError(RuntimeError):
    """Raised when no FX source is available."""


@dataclass(frozen=True)
class FxQuote:
    base: str
    quote: str
    rate: Decimal
    source: str
    fetched_at_wat: str
    rate_time_wat: str
    rate_time_utc: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rate"] = format(self.rate, "f")
        data["label"] = (
            f"1 {self.base} = {self.rate:,.4f} {self.quote}".replace(",", ",")
        )
        return data


def _format_wat(dt: datetime) -> str:
    local = dt.astimezone(WAT)
    # 10:15 AM WAT on 10 November 2026
    hour = local.strftime("%I").lstrip("0") or "0"
    ampm = local.strftime("%p")
    return f"{hour}:{local.strftime('%M')} {ampm} WAT on {local.strftime('%-d %B %Y')}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_open_er(data: dict[str, Any], base: str, quote: str) -> FxQuote:
    if data.get("result") != "success":
        raise FxError("open.er-api.com did not return success")
    rates = data.get("rates") or {}
    if quote not in rates:
        raise FxError(f"open.er-api.com has no {quote} rate")
    rate = Decimal(str(rates[quote]))
    raw_utc = data.get("time_last_update_utc") or data.get("time_last_update_unix")
    rate_dt = None
    if isinstance(raw_utc, (int, float)):
        rate_dt = datetime.fromtimestamp(int(raw_utc), tz=timezone.utc)
    elif isinstance(raw_utc, str):
        # Example: "Tue, 10 Nov 2026 00:00:01 +0000"
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                rate_dt = datetime.strptime(raw_utc, fmt)
                break
            except ValueError:
                continue
    fetched = _now()
    if rate_dt is None:
        rate_dt = fetched
    return FxQuote(
        base=base,
        quote=quote,
        rate=rate,
        source="open.er-api.com",
        fetched_at_wat=_format_wat(fetched),
        rate_time_wat=_format_wat(rate_dt),
        rate_time_utc=rate_dt.astimezone(timezone.utc).isoformat(),
    )


def _parse_frankfurter(data: dict[str, Any], base: str, quote: str) -> FxQuote:
    rates = data.get("rates") or {}
    if quote not in rates:
        raise FxError(f"Frankfurter has no {quote} rate")
    rate = Decimal(str(rates[quote]))
    rate_dt = _now()
    raw_date = data.get("date")
    if raw_date:
        try:
            rate_dt = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    fetched = _now()
    return FxQuote(
        base=base,
        quote=quote,
        rate=rate,
        source="api.frankfurter.app",
        fetched_at_wat=_format_wat(fetched),
        rate_time_wat=_format_wat(rate_dt),
        rate_time_utc=rate_dt.astimezone(timezone.utc).isoformat(),
    )


def fetch_rate(base: str, quote: str = "NGN", timeout: float = 8.0) -> FxQuote:
    base = base.upper()
    quote = quote.upper()
    if base == quote:
        now = _now()
        return FxQuote(
            base=base,
            quote=quote,
            rate=Decimal("1"),
            source="identity",
            fetched_at_wat=_format_wat(now),
            rate_time_wat=_format_wat(now),
            rate_time_utc=now.isoformat(),
        )

    key = f"{base}:{quote}"
    cached = _cache.get(key)
    now_ts = _now().timestamp()
    if cached and now_ts - cached[0] < CACHE_SECONDS:
        return cached[1]

    errors: list[str] = []
    quote_obj: FxQuote | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        try:
            response = client.get(PRIMARY_URL.format(base=base))
            response.raise_for_status()
            quote_obj = _parse_open_er(response.json(), base, quote)
        except Exception as exc:  # noqa: BLE001 - fallback is the recovery path
            errors.append(f"open.er-api.com: {exc}")
        if quote_obj is None:
            try:
                response = client.get(FALLBACK_URL.format(base=base))
                response.raise_for_status()
                quote_obj = _parse_frankfurter(response.json(), base, quote)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"frankfurter: {exc}")

    if quote_obj is None:
        raise FxError("No mid-market rate is available right now. " + " ".join(errors))

    _cache[key] = (now_ts, quote_obj)
    return quote_obj


def convert(amount: Decimal, rate: Decimal, out_currency: str) -> Decimal:
    places = 0 if out_currency.upper() in {"JPY", "HUF", "TWD", "NGN"} else 2
    step = Decimal("1") if places == 0 else Decimal("0.01")
    return (Decimal(amount) * Decimal(rate)).quantize(step, rounding=ROUND_HALF_UP)


def clear_cache() -> None:
    _cache.clear()
