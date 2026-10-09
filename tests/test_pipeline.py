import json

import pytest

from app import analyzer, pipeline
from app.serp_client import SerpResponse

FIXTURE_BY_SEARCH_NO = {
    1: "search_01_google.json", 2: "search_02_google.json", 3: "search_03_google.json",
    4: "search_04_google.json", 5: "search_05_google_news.json", 6: "search_06_google_news.json",
    7: "search_07_google_news.json", 8: "search_08_google_jobs.json", 9: "search_09_google_trends.json",
    10: "search_10_google_play.json", 11: "search_11_google_shopping.json", 12: "search_12_google.json",
    13: "search_13_google.json", 14: "search_14_google.json", 15: "search_15_google_finance.json",
    16: "search_16_google_finance.json",
}

STUB_ANALYSIS = {
    "overview": {
        "one_liner": "Acme AI builds a legal research assistant.",
        "paragraph": "Acme AI builds a legal research assistant for in-house counsel.",
        "evidence": ["e01"],
    },
    "key_facts": [{"label": "Latest round", "value": "$14M Series A", "evidence": ["e01"]}],
    "market": {"verdict": "Expanding", "verdict_text": "Rising interest.", "verdict_evidence": ["e01"], "points": []},
    "competitors": [],
    "news_highlights": [],
    "trajectory": {"headline": "Moving upmarket", "paragraph": "Forward read.", "signals": []},
    "risks": [],
    "commercial": {
        "pricing_comparison": [],
        "listed_comparables": [],
        "mismatches": [],
    },
    "diligence": [
        {
            "area": "Funding and investors",
            "topic": "Series A use of proceeds",
            "status": "Found",
            "found": "Raised $14M.",
            "question": "How much of the round is committed to headcount?",
            "why": "Burn shapes the next raise.",
            "priority": 1,
            "evidence": ["e01"],
        }
    ],
    "scorecard": [],
}


@pytest.fixture
def mock_search(monkeypatch, fixtures_dir):
    # pipeline._run_one takes the PlannedSearch itself, so it can key the fixture
    # lookup off planned.no directly rather than parsing it out of the params.
    async def fake_run_one(planned):
        from datetime import datetime, timezone

        raw = json.loads((fixtures_dir / FIXTURE_BY_SEARCH_NO[planned.no]).read_text(encoding="utf-8"))
        response = SerpResponse(engine=planned.engine, params=planned.params, status="live", raw=raw)
        return planned, response, datetime.now(timezone.utc)

    monkeypatch.setattr(pipeline, "_run_one", fake_run_one)
    yield


@pytest.fixture
def mock_analyzer(monkeypatch):
    captured = {}

    async def fake_call_entities(company, website, category, evidence_items):
        return {
            "competitors": [
                {"name": "LexBrief", "domain": "lexbrief.com"},
                {"name": "CaseMind", "domain": "casemind.io"},
                {"name": "StatuteIQ", "domain": "statuteiq.com"},
            ],
            "listed_companies": [
                {"name": "Thomson Reuters", "ticker": "TRI:NYSE"},
                {"name": "RELX", "ticker": "RELX:LON"},
            ],
        }

    async def fake_call_analysis(company, website, category, evidence_items, role_mix_note=None):
        captured["role_mix_note"] = role_mix_note
        return STUB_ANALYSIS

    monkeypatch.setattr(analyzer, "call_entities", fake_call_entities)
    monkeypatch.setattr(analyzer, "call_analysis", fake_call_analysis)
    yield captured


@pytest.mark.asyncio
async def test_pipeline_produces_16_search_log_entries(mock_search, mock_analyzer):
    briefing = await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    assert len(briefing["searches"]) == 16
    assert [s["number"] for s in briefing["searches"]] == list(range(1, 17))


@pytest.mark.asyncio
async def test_pipeline_collects_evidence_from_both_waves(mock_search, mock_analyzer):
    briefing = await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    search_nos = {e["search_no"] for e in briefing["evidence"].values()}
    assert search_nos & {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}  # wave 1
    assert search_nos & {12, 13, 14, 15, 16}  # wave 2


@pytest.mark.asyncio
async def test_pipeline_saves_and_returns_briefing(mock_search, mock_analyzer):
    from app import storage

    briefing = await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    assert storage.get_briefing(briefing["id"]) == briefing


@pytest.mark.asyncio
async def test_pipeline_reports_code_computed_role_mix(mock_search, mock_analyzer):
    briefing = await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    hiring = briefing["hiring"]
    assert hiring["total_roles"] == sum(hiring["counts"].values())
    assert "Role mix" in hiring["text"]
    assert hiring["evidence"]


@pytest.mark.asyncio
async def test_pipeline_hands_the_role_mix_to_the_analysis_call(mock_search, mock_analyzer):
    """The model must receive the counts the briefing displays, or it contradicts them."""
    await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    note = mock_analyzer["role_mix_note"]
    assert note is not None
    assert "ML and research" in note
    assert "do not ask the founders whether such roles exist" in note


@pytest.mark.asyncio
async def test_pipeline_briefing_carries_the_new_sections(mock_search, mock_analyzer):
    briefing = await pipeline.run_pipeline("Acme AI", "https://acme.ai", "AI legal research assistant")
    for key in ("overview", "key_facts", "trajectory", "news_highlights", "diligence", "hiring"):
        assert key in briefing, key
    # The old gap/question split is gone; questions now ride on the diligence rows.
    assert "gaps" not in briefing
    assert "questions" not in briefing
    assert briefing["diligence"][0]["question"]


@pytest.mark.asyncio
async def test_pipeline_rejects_blank_fields(mock_search, mock_analyzer):
    with pytest.raises(pipeline.ValidationError):
        await pipeline.run_pipeline("", "https://acme.ai", "category")


@pytest.mark.asyncio
async def test_run_pipeline_steps_progress_is_monotonic_and_ends_at_100(mock_search, mock_analyzer):
    events = [e async for e in pipeline.run_pipeline_steps("Acme AI", "https://acme.ai", "AI legal research assistant")]
    progresses = [e["progress"] for e in events]
    assert progresses == sorted(progresses)
    assert progresses[-1] == 100
    assert all("label" in e for e in events)


@pytest.mark.asyncio
async def test_run_pipeline_steps_only_last_event_carries_briefing(mock_search, mock_analyzer):
    events = [e async for e in pipeline.run_pipeline_steps("Acme AI", "https://acme.ai", "AI legal research assistant")]
    assert all("briefing" not in e for e in events[:-1])
    assert "briefing" in events[-1]
    assert events[-1]["briefing"]["company"] == "Acme AI"


@pytest.mark.asyncio
async def test_run_pipeline_steps_raises_validation_error_before_any_event(mock_search, mock_analyzer):
    gen = pipeline.run_pipeline_steps("", "https://acme.ai", "category")
    with pytest.raises(pipeline.ValidationError):
        await gen.__anext__()
