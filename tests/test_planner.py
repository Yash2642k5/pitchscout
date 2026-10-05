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


def test_plan_wave_2_has_5_searches_numbered_12_to_16():
    competitors = [{"name": "LexBrief"}, {"name": "CaseMind"}, {"name": "StatuteIQ"}]
    tickers = ["TRI:NYSE", "RELX:LON"]
    searches = planner.plan_wave_2(competitors, tickers)
    assert [s.no for s in searches] == [12, 13, 14, 15, 16]
    assert [s.engine for s in searches] == ["google", "google", "google", "google_finance", "google_finance"]
    assert searches[0].params["q"] == "LexBrief pricing plans"
    assert searches[3].params["q"] == "TRI:NYSE"


def test_plan_wave_2_handles_missing_entities_gracefully():
    searches = planner.plan_wave_2([], [])
    assert len(searches) == 5
    assert all(s.params["q"] == "" for s in searches)


def test_plan_all_returns_16_searches():
    competitors = [{"name": "LexBrief"}, {"name": "CaseMind"}, {"name": "StatuteIQ"}]
    tickers = ["TRI:NYSE", "RELX:LON"]
    searches = planner.plan_all("Acme AI", "https://acme.ai", "AI legal research assistant", competitors, tickers)
    assert len(searches) == 16
    assert [s.no for s in searches] == list(range(1, 17))
