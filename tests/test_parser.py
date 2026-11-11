from datetime import datetime
from zoneinfo import ZoneInfo

from app.envutil import read_env
from app.parser import maybe_refine_with_llm, parse_invoice

WAT = ZoneInfo("Africa/Lagos")
TUESDAY = datetime(2026, 11, 10, 9, 0, tzinfo=WAT)  # A Tuesday


def parse(text, now=TUESDAY):
    return parse_invoice(text, now=now)


def test_logo_design_for_sarah():
    result = parse("Logo design for Sarah, 150 USD, due Friday")
    assert result.ok
    assert result.client == "Sarah"
    assert result.items == "Logo design"
    assert result.amount == "150.00"
    assert result.currency == "USD"
    assert result.due_date == "2026-11-13"
    assert "Friday" in (result.due_date_label or "")
    assert result.source == "rules"


def test_naira_website_invoice():
    result = parse("Website redesign for Chidi, ₦450,000, due 20 November")
    assert result.ok
    assert result.client == "Chidi"
    assert "Website" in (result.items or "")
    assert result.amount == "450000"
    assert result.currency == "NGN"
    assert result.due_date == "2026-11-20"
    assert any("Naira" in w or "NGN" in w for w in result.warnings)


def test_structured_invoice():
    text = "Bill to: Acme Studio\nDescription: 3 social media posts\nTotal: $80\nDue date: tomorrow"
    result = parse(text)
    assert result.ok
    assert result.client == "Acme Studio"
    assert result.items == "3 social media posts"
    assert result.amount == "80.00"
    assert result.currency == "USD"
    assert result.due_date == "2026-11-11"


def test_euros_and_tomorrow_in_chat():
    result = parse("can you invoice me 200 euros for the brand guidelines? due tomorrow")
    assert result.ok
    assert result.amount == "200.00"
    assert result.currency == "EUR"
    assert result.due_date == "2026-11-11"
    assert "brand guidelines" in (result.items or "").lower()


def test_client_is_pattern():
    result = parse("Please pay GBP 75 for copywriting, client is Nora, due next week")
    assert result.ok
    assert result.currency == "GBP"
    assert result.amount == "75.00"
    assert result.client == "Nora"
    assert result.due_date == "2026-11-17"


def test_due_friday_on_friday_is_today():
    friday = datetime(2026, 11, 13, 15, 0, tzinfo=WAT)
    result = parse("Logo for Sam, $40, due Friday", now=friday)
    assert result.due_date == "2026-11-13"


def test_missing_amount():
    result = parse("Invoice for Julia, due Friday")
    assert not result.ok
    assert result.amount is None
    assert result.client == "Julia"
    assert any("amount" in w.lower() for w in result.warnings)


def test_assumed_usd_when_currency_missing():
    result = parse("Amount: 150 for a landing page, client: Tunde")
    assert result.ok
    assert result.amount == "150.00"
    assert result.currency == "USD"
    assert result.currency_assumed
    assert result.client == "Tunde"


def test_k_suffix_naira():
    result = parse("Flyer design for Tunde, 350k naira, due Nov 12")
    assert result.ok
    assert result.currency == "NGN"
    assert result.amount == "350000"
    assert result.client == "Tunde"
    assert result.due_date == "2026-11-12"


def test_empty_text():
    result = parse("   ")
    assert not result.ok
    assert "Paste" in result.warnings[0]


def test_day_first_numeric_date():
    result = parse("Portrait shoot for Ama, 120 USD, due 15/11/2026")
    assert result.due_date == "2026-11-15"
    assert result.client == "Ama"


def test_llm_join_reads_split_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_P0", "abcd")
    monkeypatch.setenv("GROQ_API_KEY_P1", "efgh")
    assert read_env("GROQ_API_KEY") == "abcdefgh"


def test_llm_not_used_without_key():
    result = parse("Logo design for Sarah, 150 USD, due Friday")
    refined = maybe_refine_with_llm(result, "Logo design for Sarah, 150 USD, due Friday", now=TUESDAY)
    assert refined.source == "rules"
    assert refined.client == "Sarah"


def test_llm_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("httpx.post", boom)
    result = parse("Logo design for Sarah, 150 USD, due Friday")
    refined = maybe_refine_with_llm(result, "Logo design for Sarah, 150 USD, due Friday", now=TUESDAY)
    assert refined.source == "rules"
    assert refined.client == "Sarah"
    assert refined.amount == "150.00"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_llm_refine_sets_source_and_fills_gaps(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")

    def fake_post(url, **kwargs):
        assert "api.groq.com" in url
        assert kwargs["json"]["model"] == "openai/gpt-oss-120b"
        return _FakeResponse({
            "choices": [{
                "message": {
                    "content": (
                        '{"client":"Sarah","items":["Logo"],'
                        '"amount":"150","currency":"USD","due_date":"2026-11-13"}'
                    )
                }
            }]
        })

    monkeypatch.setattr("httpx.post", fake_post)
    # This text has no amount, so the model has a gap to fill.
    result = parse("Love the logo! PayPal ok? need it by friday - Sarah")
    assert result.amount is None
    refined = maybe_refine_with_llm(
        result,
        "Love the logo! Sending $150 now. PayPal ok? need it by friday - Sarah",
        now=TUESDAY,
    )
    assert refined.source == "rules+llm"
    assert refined.ok
    assert refined.client == "Sarah"
    assert refined.amount == "150.00"
    assert refined.currency == "USD"
    assert refined.due_date == "2026-11-13"
    # Existing rule-based fields are kept; the model only fills gaps.
    assert refined.items == result.items


def test_llm_items_list_is_joined(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def fake_post(url, **kwargs):
        return _FakeResponse({
            "choices": [{
                "message": {
                    "content": '{"client":"Sarah","items":["Logo","revisions"],"amount":null,"currency":null,"due_date":null}'
                }
            }]
        })

    monkeypatch.setattr("httpx.post", fake_post)
    result = parse("Invoice for Sarah, due Friday")
    refined = maybe_refine_with_llm(result, "Invoice for Sarah, due Friday", now=TUESDAY)
    assert refined.source == "rules+llm"
    assert refined.items == "Logo, revisions"
    assert refined.client == "Sarah"
