from datetime import datetime, timezone

import pytest

from app.evidence import IdCounter
from app.normalizers import normalize

RETRIEVED_AT = datetime(2026, 1, 15, tzinfo=timezone.utc)
COMPANY = "Acme AI"
WEBSITE = "https://acme.ai"
CATEGORY = "AI legal research assistant"

REQUIRED_KEYS = {
    "id", "search_no", "engine", "title", "snippet", "url",
    "source_domain", "published_date", "retrieved_at", "stale",
}

FIXTURE_CASES = [
    (1, "google", "search_01_google.json"),
    (2, "google", "search_02_google.json"),
    (3, "google", "search_03_google.json"),
    (4, "google", "search_04_google.json"),
    (5, "google_news", "search_05_google_news.json"),
    (6, "google_news", "search_06_google_news.json"),
    (7, "google_news", "search_07_google_news.json"),
    (8, "google_jobs", "search_08_google_jobs.json"),
    (9, "google_trends", "search_09_google_trends.json"),
    (10, "google_play", "search_10_google_play.json"),
    (11, "google_shopping", "search_11_google_shopping.json"),
    (12, "google", "search_12_google.json"),
    (13, "google", "search_13_google.json"),
    (14, "google", "search_14_google.json"),
    (15, "google_finance", "search_15_google_finance.json"),
    (16, "google", "search_16_google.json"),
    (17, "google", "search_17_google.json"),
    (18, "google_news", "search_18_google_news.json"),
]


@pytest.mark.parametrize("search_no,engine,filename", FIXTURE_CASES)
def test_every_fixture_converts_to_schema_valid_evidence(fixtures_dir, search_no, engine, filename):
    import json

    raw = json.loads((fixtures_dir / filename).read_text(encoding="utf-8"))
    counter = IdCounter()
    items = normalize(raw, search_no, engine, RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY)
    for item in items:
        assert REQUIRED_KEYS.issubset(item.keys())
        assert item["search_no"] == search_no
        assert item["engine"] == engine
        assert isinstance(item["title"], str)
        assert isinstance(item["stale"], bool)


def test_normalize_caps_at_max_results():
    raw = {
        "organic_results": [
            {"title": f"Acme AI result {i}", "link": f"https://acme.ai/{i}", "snippet": "Acme AI info"}
            for i in range(25)
        ]
    }
    counter = IdCounter()
    items = normalize(raw, 1, "google", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY)
    assert len(items) <= 8


def test_empty_response_converts_to_empty_list():
    counter = IdCounter()
    assert normalize({}, 1, "google", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY) == []
    assert normalize(None, 1, "google", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY) == []
    assert normalize({"organic_results": []}, 3, "google", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY) == []


def test_unknown_engine_returns_empty_list():
    counter = IdCounter()
    assert normalize({"anything": 1}, 1, "bing", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY) == []


def test_google_jobs_titles_are_usable_for_role_classification(fixtures_dir):
    import json

    raw = json.loads((fixtures_dir / "search_08_google_jobs.json").read_text(encoding="utf-8"))
    counter = IdCounter()
    items = normalize(raw, 8, "google_jobs", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY)
    titles = [item["title"] for item in items]
    assert "Senior Machine Learning Engineer" in titles
    assert "Backend Engineer" in titles


def test_google_trends_produces_one_summary_item(fixtures_dir):
    import json

    raw = json.loads((fixtures_dir / "search_09_google_trends.json").read_text(encoding="utf-8"))
    counter = IdCounter()
    items = normalize(raw, 9, "google_trends", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY)
    assert len(items) == 1
    assert "rising" in items[0]["snippet"] or "declining" in items[0]["snippet"] or "flat" in items[0]["snippet"]


def test_google_finance_produces_one_summary_item(fixtures_dir):
    import json

    raw = json.loads((fixtures_dir / "search_15_google_finance.json").read_text(encoding="utf-8"))
    counter = IdCounter()
    items = normalize(raw, 15, "google_finance", RETRIEVED_AT, counter, COMPANY, WEBSITE, CATEGORY)
    assert len(items) == 1
    assert "Price" in items[0]["snippet"]
