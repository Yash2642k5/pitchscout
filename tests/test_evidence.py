from datetime import datetime, timedelta, timezone

from app.evidence import (
    IdCounter,
    build_evidence_item,
    is_stale,
    parse_date,
    passes_name_filter,
    registrable_domain,
)


def test_id_counter_increments_zero_padded():
    counter = IdCounter()
    assert counter.next_id() == "e01"
    assert counter.next_id() == "e02"


def test_registrable_domain_strips_www_and_path():
    assert registrable_domain("https://www.acme.ai/pricing") == "acme.ai"
    assert registrable_domain("https://techcrunch.com/2025/11/20/x") == "techcrunch.com"


def test_registrable_domain_handles_two_label_public_suffix():
    assert registrable_domain("https://example.co.in/page") == "example.co.in"


def test_registrable_domain_empty_for_blank_url():
    assert registrable_domain("") == ""


def test_parse_date_relative():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert parse_date("5 days ago", retrieved) == (retrieved - timedelta(days=5)).date().isoformat()


def test_parse_date_absolute_month_day_year():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert parse_date("Nov 20, 2025", retrieved) == "2025-11-20"


def test_parse_date_handles_google_news_timestamp():
    # SerpApi's google_news engine stamps a time and zone onto the date; until this was
    # handled every news item came back undated, so nothing could ever be marked stale.
    retrieved = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert parse_date("10/01/2026, 08:35 PM, +0000 UTC", retrieved) == "2026-10-01"
    assert parse_date("Jul 21, 2026, 07:00 AM, +0000 UTC", retrieved) == "2026-07-21"


def test_google_news_timestamp_feeds_staleness():
    retrieved = datetime(2026, 10, 9, tzinfo=timezone.utc)
    parsed = parse_date("07/21/2021, 07:00 AM, +0000 UTC", retrieved)
    assert parsed == "2021-07-21"
    assert is_stale(parsed, retrieved) is True


def test_parse_date_none_when_missing():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert parse_date(None, retrieved) is None
    assert parse_date("", retrieved) is None


def test_is_stale_true_when_over_365_days():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert is_stale("2024-01-01", retrieved) is True


def test_is_stale_false_when_recent():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert is_stale("2025-12-01", retrieved) is False


def test_is_stale_false_when_missing():
    retrieved = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert is_stale(None, retrieved) is False


def test_name_filter_applies_only_to_1_2_5_6():
    assert passes_name_filter(3, "Acme AI", "https://acme.ai", "Unrelated title", "no mention", "https://other.com") is True


def test_name_filter_keeps_result_mentioning_company():
    assert passes_name_filter(1, "Acme AI", "https://acme.ai", "Acme AI raises funding", "...", "https://techcrunch.com") is True


def test_name_filter_keeps_result_from_company_domain():
    assert passes_name_filter(1, "Acme AI", "https://acme.ai", "Pricing", "no mention here", "https://acme.ai/pricing") is True


def test_name_filter_drops_irrelevant_result():
    assert passes_name_filter(1, "Acme AI", "https://acme.ai", "Totally unrelated", "nothing relevant", "https://other.com") is False


def test_build_evidence_item_schema():
    counter = IdCounter()
    retrieved_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
    item = build_evidence_item(
        counter, 1, "google", "Acme AI raises funding", "snippet text",
        "https://techcrunch.com/x", "Nov 20, 2025", retrieved_at,
    )
    assert item == {
        "id": "e01",
        "search_no": 1,
        "engine": "google",
        "title": "Acme AI raises funding",
        "snippet": "snippet text",
        "url": "https://techcrunch.com/x",
        "source_domain": "techcrunch.com",
        "published_date": "2025-11-20",
        "retrieved_at": retrieved_at.isoformat(),
        "stale": False,
    }
