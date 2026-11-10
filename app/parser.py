"""Rule-based invoice and chat-message parser.

This is the default "AI" step. It uses deterministic pattern matching, not a
hosted model, so it works with no API key. An optional OpenAI-compatible model
can refine the parse when OPENAI_API_KEY or GROQ_API_KEY is set.

The parser looks for a client, line items, an amount and currency, and a due
date. Dates are resolved in Africa/Lagos (WAT).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.parser import parse as dateutil_parse
from dateutil.relativedelta import relativedelta, FR, MO, SA, SU, TH, TU, WE

WAT = ZoneInfo("Africa/Lagos")

CURRENCY_WORDS = {
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "bucks": "USD",
    "us$": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "sterling": "GBP",
    "ngn": "NGN",
    "naira": "NGN",
    "cad": "CAD",
    "aud": "AUD",
    "c$": "CAD",
    "a$": "AUD",
}

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₦": "NGN",
}

# Word-shaped codes we should not treat as a client name.
WEEKDAYS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
}

STOP_CLIENT = WEEKDAYS | {
    "due", "by", "on", "the", "a", "an", "and", "for", "invoice", "total",
    "amount", "payment", "please", "pay", "usd", "eur", "gbp", "ngn", "naira",
    "dollars", "dollar", "euros", "euro", "pounds", "tomorrow", "today",
    "next", "this", "week", "month",
}

WEEKDAY_INDEX = {
    "monday": MO, "mon": MO,
    "tuesday": TU, "tue": TU, "tues": TU,
    "wednesday": WE, "wed": WE,
    "thursday": TH, "thu": TH, "thur": TH, "thurs": TH,
    "friday": FR, "fri": FR,
    "saturday": SA, "sat": SA,
    "sunday": SU, "sun": SU,
}


@dataclass
class ParseResult:
    ok: bool
    client: str | None = None
    items: str | None = None
    amount: str | None = None
    currency: str | None = None
    currency_assumed: bool = False
    due_date: str | None = None  # ISO date YYYY-MM-DD
    due_date_label: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    source: str = "rules"
    raw_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_wat(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(WAT)
    if now.tzinfo is None:
        return now.replace(tzinfo=WAT)
    return now.astimezone(WAT)


def _clean(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _parse_number(raw: str, suffix: str = "") -> Decimal | None:
    raw = raw.strip().replace(" ", "")
    if not raw:
        return None
    # European 1.500,00 vs US 1,500.00. If both separators exist, the last is decimal.
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(",") == 1 and len(raw.split(",")[1]) in (1, 2):
        raw = raw.replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", "")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    suffix = suffix.lower()
    if suffix == "k":
        value *= 1000
    elif suffix in {"m", "mn"}:
        value *= 1_000_000
    return value


def _extract_amount_and_currency(text: str) -> tuple[Decimal | None, str | None, bool]:
    """Return (amount, currency, assumed)."""
    assumed = False
    # Symbol + number, optional k/m suffix. Allow ₦450,000 or $150.00
    symbol_re = re.compile(
        r"(?P<sym>[₦$€£])\s*(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?P<suf>[kKmM])?\b"
    )
    # Number then currency word/code
    after_re = re.compile(
        r"(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?P<suf>[kKmM])?\s*(?P<cur>USD|EUR|GBP|NGN|CAD|AUD|dollars?|bucks|euros?|pounds?|naira|sterling)\b",
        re.I,
    )
    # Currency then number
    before_re = re.compile(
        r"\b(?P<cur>USD|EUR|GBP|NGN|CAD|AUD|US\$)\s*"
        r"(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?P<suf>[kKmM])?\b",
        re.I,
    )
    # Labelled amount without currency: Amount: 150 / Total 150
    labelled_re = re.compile(
        r"\b(?:amount|total|fee|price|invoice(?:\s+total)?|pay(?:ment)?)\s*[:=]?\s*"
        r"(?P<sym>[₦$€£])?\s*"
        r"(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?P<suf>[kKmM])?\s*"
        r"(?P<cur>USD|EUR|GBP|NGN|CAD|AUD|dollars?|bucks|euros?|pounds?|naira|sterling)?",
        re.I,
    )

    candidates: list[tuple[int, Decimal, str | None]] = []

    for match in symbol_re.finditer(text):
        value = _parse_number(match.group("num"), match.group("suf") or "")
        if value is None:
            continue
        code = CURRENCY_SYMBOLS[match.group("sym")]
        candidates.append((match.start(), value, code))

    for match in after_re.finditer(text):
        value = _parse_number(match.group("num"), match.group("suf") or "")
        if value is None:
            continue
        word = match.group("cur").lower()
        code = CURRENCY_WORDS.get(word, word.upper())
        candidates.append((match.start(), value, code))

    for match in before_re.finditer(text):
        value = _parse_number(match.group("num"), match.group("suf") or "")
        if value is None:
            continue
        word = match.group("cur").lower().replace("us$", "usd")
        code = CURRENCY_WORDS.get(word, word.upper())
        candidates.append((match.start(), value, code))

    if candidates:
        # Prefer a match that has a currency, then the last mention (often the total).
        with_cur = [c for c in candidates if c[2]]
        pool = with_cur or candidates
        _, value, code = pool[-1]
        return value, code, False

    for match in labelled_re.finditer(text):
        value = _parse_number(match.group("num"), match.group("suf") or "")
        if value is None:
            continue
        if match.group("sym"):
            return value, CURRENCY_SYMBOLS[match.group("sym")], False
        if match.group("cur"):
            word = match.group("cur").lower()
            return value, CURRENCY_WORDS.get(word, word.upper()), False
        assumed = True
        return value, "USD", assumed

    return None, None, False


def _title_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" \t,.-")
    # Keep existing caps for acronyms, otherwise title case.
    if name.isupper() and len(name) <= 6:
        return name
    return " ".join(
        w if (w.isupper() and len(w) > 1) else w[:1].upper() + w[1:]
        for w in name.split(" ")
        if w
    )


def _looks_like_name(text: str) -> bool:
    if not text:
        return False
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words or len(words) > 5:
        return False
    if any(re.search(r"\d", w) for w in words):
        return False
    lowered = {re.sub(r"[^a-zA-Z]", "", w).lower() for w in words}
    if lowered & STOP_CLIENT:
        return False
    return True


def _extract_client(text: str) -> str | None:
    # Apply line by line for labelled forms
    for line in text.splitlines():
        match = re.match(
            r"(?i)^\s*(?:bill\s+to|invoiced?\s+to|invoice\s+for|client|customer|"
            r"customer\s+name|to)\s*[:\-]\s*(.+?)\s*$",
            line,
        )
        if match and _looks_like_name(match.group(1)):
            return _title_name(match.group(1))

    # "client is Nora" / "client: Nora"
    match = re.search(
        r"(?i)\b(?:client|customer|bill(?:ed)?\s+to)\s*(?:is|:|-)\s+([A-Za-z][A-Za-z.''\-]+(?:\s+[A-Za-z][A-Za-z.''\-]+){0,3})",
        text,
    )
    if match and _looks_like_name(match.group(1)):
        return _title_name(match.group(1))

    # "for Sarah" but not "invoice for website" or "for the logo"
    for match in re.finditer(
        r"(?i)\bfor\s+([A-Za-z][A-Za-z.''\-]+(?:\s+[A-Za-z][A-Za-z.''\-]+){0,3})",
        text,
    ):
        name = match.group(1).strip()
        # Cut at a trailing due/amount clause if captured
        name = re.split(r"(?i)\b(due|by|amount|total|usd|eur|ngn|naira)\b", name)[0].strip()
        if _looks_like_name(name):
            # Avoid "for logo" / "for website redesign" type phrases (common nouns)
            first = name.split()[0].lower()
            common_nouns = {
                "logo", "website", "web", "app", "mobile", "brand", "social",
                "flyer", "copywriting", "design", "redesign", "the", "a", "an",
                "my", "our", "your", "this", "that", "invoice", "payment",
            }
            if first not in common_nouns:
                return _title_name(name)
    return None


def _extract_items(text: str, client: str | None) -> str | None:
    for line in text.splitlines():
        match = re.match(
            r"(?i)^\s*(?:item|items|description|service|work|project|for)\s*[:\-]\s*(.+?)\s*$",
            line,
        )
        if match:
            item = match.group(1).strip()
            if item:
                return _clean_item(item, client)

    # "Logo design for Sarah, 150 USD"
    match = re.search(
        r"(?is)(?:^|\n)(?:hey[,!]?\s+|hi[,!]?\s+|hello[,!]?\s+|please\s+)?"
        r"(?:can you (?:invoice|send|bill) (?:me )?)?"
        r"(.+?)\s+for\s+[A-Za-z]",
        text.strip(),
    )
    if match:
        item = _clean_item(match.group(1), client)
        if item and not re.fullmatch(r"(?i)(invoice|invoices|bill|payment)", item):
            return item

    # First meaningful line
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"(?i)^(invoice|bill to|due|total|amount|client|date|to:)\b", stripped):
            continue
        if re.fullmatch(r"[\d₦$€£.,\s]+", stripped):
            continue
        return _clean_item(stripped, client)
    return None


def _clean_item(item: str, client: str | None) -> str:
    item = _clean(item)
    item = re.sub(r"(?i)^\s*(please\s+)?(pay|invoice|bill)(\s+me)?\s+(for\s+)?", "", item)
    item = re.sub(r"(?i)^\s*can you (?:invoice|send|bill)(?: me)?\s+", "", item)
    if client:
        item = re.sub(re.escape(client), "", item, flags=re.I)
    item = re.sub(
        r"(?i)\b(due|by)\b.*$",
        "",
        item,
    )
    item = re.sub(
        r"(?:[₦$€£]\s*\d[\d.,]*|\d[\d.,]*\s*(?:k|m)?\s*(?:USD|EUR|GBP|NGN|CAD|AUD|dollars?|naira|euros?|pounds?)?)\s*$",
        "",
        item,
        flags=re.I,
    )
    item = item.strip(" \t,.-:")
    if not item:
        return ""
    if item[0].islower():
        item = item[0].upper() + item[1:]
    return item


def _next_weekday(now: datetime, weekday_token: str) -> date:
    rel = WEEKDAY_INDEX[weekday_token.lower()]
    today = now.date()
    # dateutil's weekday(0) is the next such day, not today if today matches.
    # "due Friday" on a Friday should mean today if said in the morning? More
    # natural is today if it is that weekday, otherwise the coming one.
    if today.strftime("%A").lower().startswith(weekday_token.lower()[:3]):
        return today
    nxt = now + relativedelta(weekday=rel(0))
    return nxt.date()


def _extract_due_date(text: str, now: datetime) -> tuple[date | None, str | None]:
    today = now.date()
    lowered = text.lower()

    # Labelled due / deadline
    labelled = re.search(
        r"(?i)\b(?:due(?:\s+date)?|deadline|pay(?:able)?\s+by|by)\s*[:\-]?\s*(.+)$",
        text,
        re.M,
    )
    snippet = labelled.group(1).strip() if labelled else ""

    def from_relative(chunk: str) -> date | None:
        chunk = chunk.lower()
        if re.search(r"\btoday\b", chunk):
            return today
        if re.search(r"\btomorrow\b", chunk):
            return today + timedelta(days=1)
        if re.search(r"\bnext week\b", chunk):
            return today + timedelta(days=7)
        m = re.search(
            r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
            chunk,
        )
        if m:
            token = m.group(1)
            target = _next_weekday(now, token)
            if re.search(r"\bnext\s+" + re.escape(token) + r"\b", chunk) and target == today:
                # "next Friday" on a Friday: the following Friday
                return today + timedelta(days=7)
            return target
        return None

    search_space = snippet or text
    rel = from_relative(search_space)
    if rel:
        return rel, _format_due(rel)

    # Explicit dates: 20 November, Nov 20, 20/11/2026, 2026-11-20, 15 Nov 2026
    date_patterns = [
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        r"\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)(?:\s+\d{2,4})?)\b",
        r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{2,4})?)\b",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, search_space, flags=re.I)
        if not match:
            continue
        raw = match.group(1)
        parsed = _safe_parse_date(raw, now)
        if parsed:
            return parsed, _format_due(parsed)
    return None, None


def _safe_parse_date(raw: str, now: datetime) -> date | None:
    raw = raw.strip()
    # Prefer day-first for numeric dates, common in Nigeria.
    try:
        if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", raw):
            parsed = dateutil_parse(raw, dayfirst=True, yearfirst=False, fuzzy=False).date()
        else:
            parsed = dateutil_parse(raw, dayfirst=True, default=now.replace(tzinfo=None), fuzzy=False).date()
    except (ValueError, OverflowError, TypeError):
        return None
    # If the user omitted a year and the date already passed, roll to next year.
    if not re.search(r"\d{4}", raw) and parsed < now.date() and (now.date() - parsed).days > 1:
        try:
            parsed = parsed.replace(year=parsed.year + 1)
        except ValueError:
            pass
    return parsed


def _format_due(value: date) -> str:
    # "Friday, 13 November 2026"
    return value.strftime("%A, %-d %B %Y")


def _confidence(result: ParseResult) -> float:
    score = 0.0
    if result.amount:
        score += 0.45
    if result.currency and not result.currency_assumed:
        score += 0.2
    elif result.currency:
        score += 0.08
    if result.client:
        score += 0.15
    if result.items:
        score += 0.1
    if result.due_date:
        score += 0.1
    return round(min(score, 0.99), 2)


def parse_invoice(text: str, now: datetime | None = None) -> ParseResult:
    raw = text or ""
    cleaned = _clean(raw)
    current = now_wat(now)
    warnings: list[str] = []

    if not cleaned:
        return ParseResult(
            ok=False,
            warnings=["Paste an invoice or a short chat message first."],
            raw_text=raw,
        )

    amount, currency, assumed = _extract_amount_and_currency(cleaned)
    client = _extract_client(cleaned)
    items = _extract_items(cleaned, client)
    due, due_label = _extract_due_date(cleaned, current)

    if assumed:
        warnings.append(
            "No currency was found, so USD was assumed. Change this before you "
            "create a payment link if that is wrong."
        )
    if currency == "NGN":
        warnings.append(
            "This invoice is in Naira. PayPal does not settle in NGN, so the "
            "payment link will be created in USD at the mid-market rate."
        )

    amount_str = None
    if amount is not None:
        # Keep two decimals for most currencies, none for obvious whole Naira.
        if currency == "NGN" and amount == amount.to_integral():
            amount_str = format(amount.quantize(Decimal("1")), "f")
        else:
            amount_str = format(amount.quantize(Decimal("0.01")), "f")

    result = ParseResult(
        ok=amount is not None,
        client=client,
        items=items or None,
        amount=amount_str,
        currency=currency,
        currency_assumed=assumed,
        due_date=due.isoformat() if due else None,
        due_date_label=due_label,
        warnings=warnings,
        source="rules",
        raw_text=raw,
    )
    if amount is None:
        result.warnings.append(
            "I could not find an amount. Add one, for example 150 USD or ₦200,000."
        )
    result.confidence = _confidence(result)
    return result


def maybe_refine_with_llm(result: ParseResult, text: str, now: datetime | None = None) -> ParseResult:
    """Optionally refine a parse with an OpenAI-compatible API. Failures are ignored."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return result
    base = os.environ.get("OPENAI_BASE_URL")
    if not base and os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        base = "https://api.groq.com/openai/v1"
    base = (base or "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL") or os.environ.get("GROQ_MODEL") or "gpt-4o-mini"
    current = now_wat(now)
    prompt = {
        "role": "system",
        "content": (
            "Extract invoice fields from a freelancer chat or invoice. "
            "Return only JSON with keys client, items, amount, currency, due_date. "
            "amount must be a number string. currency must be an ISO code. "
            "due_date must be YYYY-MM-DD in Africa/Lagos. Today is "
            f"{current.date().isoformat()}. Use null for missing fields."
        ),
    }
    try:
        import httpx

        response = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [prompt, {"role": "user", "content": text[:4000]}],
            },
            timeout=8.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except Exception:
        return result

    refined = ParseResult(**{**result.as_dict()})
    if data.get("client") and not refined.client:
        refined.client = str(data["client"]).strip()
    if data.get("items") and not refined.items:
        refined.items = str(data["items"]).strip()
    if data.get("amount") and not refined.amount:
        try:
            value = Decimal(str(data["amount"]).replace(",", ""))
            refined.amount = format(value.quantize(Decimal("0.01")), "f")
            refined.ok = True
        except (InvalidOperation, ValueError, TypeError):
            pass
    if data.get("currency") and (not refined.currency or refined.currency_assumed):
        code = str(data["currency"]).upper().strip()
        if re.fullmatch(r"[A-Z]{3}", code):
            refined.currency = code
            refined.currency_assumed = False
    if data.get("due_date") and not refined.due_date:
        raw = str(data["due_date"])
        try:
            due = date.fromisoformat(raw)
            refined.due_date = due.isoformat()
            refined.due_date_label = _format_due(due)
        except ValueError:
            pass
    refined.source = "rules+llm"
    refined.confidence = _confidence(refined)
    # Drop warnings that no longer apply
    if refined.amount:
        refined.warnings = [w for w in refined.warnings if "could not find an amount" not in w]
    return refined
