from app import storage


def test_usage_starts_at_zero():
    assert storage.get_usage() == 0


def test_increment_usage_increments():
    storage.increment_usage()
    storage.increment_usage()
    assert storage.get_usage() == 2


def test_cache_round_trip():
    assert storage.get_cached("missing-key") is None
    storage.set_cached("key-1", "google", {"organic_results": []})
    assert storage.get_cached("key-1") == {"organic_results": []}


def test_cache_hit_leaves_usage_counter_unchanged():
    storage.set_cached("key-1", "google", {"organic_results": [1]})
    before = storage.get_usage()
    cached = storage.get_cached("key-1")
    assert cached == {"organic_results": [1]}
    assert storage.get_usage() == before


def test_get_budget_reads_env(monkeypatch):
    monkeypatch.setenv("SEARCH_BUDGET", "42")
    assert storage.get_budget() == 42


def test_save_and_get_briefing():
    briefing = {"id": "abc-123", "company": "Acme AI", "generated_at": "2026-01-15T00:00:00+00:00"}
    storage.save_briefing(briefing)
    assert storage.get_briefing("abc-123") == briefing
    assert storage.get_briefing("missing") is None


def test_list_briefings_returns_summaries_sorted_newest_first():
    storage.save_briefing({"id": "a", "company": "Old Co", "generated_at": "2025-01-01T00:00:00+00:00"})
    storage.save_briefing({"id": "b", "company": "New Co", "generated_at": "2026-01-01T00:00:00+00:00"})
    items = storage.list_briefings()
    assert [i["id"] for i in items] == ["b", "a"]
    assert all(set(i.keys()) == {"id", "company", "generated_at"} for i in items)


def test_find_briefing_by_company_case_insensitive():
    storage.save_briefing({"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"})
    assert storage.find_briefing_by_company("acme ai")["id"] == "x"
    assert storage.find_briefing_by_company("ACME AI")["id"] == "x"
    assert storage.find_briefing_by_company("Nonexistent Co") is None
