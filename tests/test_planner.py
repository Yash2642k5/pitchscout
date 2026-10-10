from app import planner


def test_plan_wave_1_has_11_searches_numbered_1_to_11():
    searches = planner.plan_wave_1("Acme AI", "https://acme.ai", "AI legal research assistant")
    assert len(searches) == 11
    assert [s.no for s in searches] == list(range(1, 12))
    assert all(s.wave == 1 for s in searches)


def test_plan_wave_1_engines_match_search_plan():
    searches = planner.plan_wave_1("Acme AI", "https://acme.ai", "AI legal research assistant")
    engines = [s.engine for s in searches]
    assert engines == [
        "google", "google", "google", "google",
        "google_news", "google_news", "google_news",
        "google_jobs", "google_trends", "google_play", "google_shopping",
    ]


def test_plan_wave_2_has_7_searches_numbered_12_to_18():
    competitors = [{"name": "LexBrief"}, {"name": "CaseMind"}, {"name": "StatuteIQ"}]
    searches = planner.plan_wave_2("Acme AI", "AI legal research", competitors, "ACME:NASDAQ")
    assert [s.no for s in searches] == [12, 13, 14, 15, 16, 17, 18]
    assert [s.engine for s in searches] == [
        "google", "google", "google", "google_finance", "google", "google", "google_news",
    ]
    assert searches[0].params["q"] == "LexBrief pricing plans"
    assert searches[3].params["q"] == "ACME:NASDAQ"


def test_plan_wave_2_asks_the_stock_graph_for_a_year_not_a_day():
    searches = planner.plan_wave_2("Acme AI", "AI legal research", [], "ACME:NASDAQ")
    finance = next(s for s in searches if s.engine == "google_finance")
    assert finance.params["window"] == "1Y"


def test_plan_wave_2_searches_for_share_and_brand_value_figures():
    searches = planner.plan_wave_2("Acme AI", "AI legal research", [])
    queries = {s.no: s.params["q"] for s in searches}
    assert "market share" in queries[16] and "AI legal research" in queries[16]
    assert "brand value" in queries[17]
    assert "valuation" in queries[18]


def test_plan_wave_2_without_a_ticker_leaves_the_finance_search_blank():
    searches = planner.plan_wave_2("Acme AI", "AI legal research", [])
    finance = next(s for s in searches if s.engine == "google_finance")
    assert finance.params["q"] == ""
    assert "window" not in finance.params


def test_plan_wave_2_handles_missing_competitors_gracefully():
    searches = planner.plan_wave_2("Acme AI", "AI legal research", [])
    assert len(searches) == 7
    assert [s.params["q"] for s in searches[:3]] == ["", "", ""]


def test_plan_all_returns_18_searches():
    competitors = [{"name": "LexBrief"}, {"name": "CaseMind"}, {"name": "StatuteIQ"}]
    searches = planner.plan_all(
        "Acme AI", "https://acme.ai", "AI legal research assistant", competitors, "ACME:NASDAQ"
    )
    assert len(searches) == 18
    assert [s.no for s in searches] == list(range(1, 19))
