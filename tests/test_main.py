import json

import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.pipeline import ValidationError
from app.serp_client import BudgetExceeded


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "false")
    return TestClient(main.app)


def test_post_briefing_missing_field_returns_422(client):
    res = client.post("/api/briefing", json={"company": "Acme AI", "website": "https://acme.ai"})
    assert res.status_code == 422


def test_post_briefing_blank_field_returns_422(client):
    res = client.post(
        "/api/briefing",
        json={"company": "", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 422


def test_post_briefing_success(client, monkeypatch):
    fake_briefing = {"id": "abc", "company": "Acme AI", "searches": []}

    async def fake_run_pipeline(company, website, category, gl):
        return fake_briefing

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    res = client.post(
        "/api/briefing",
        json={"company": "Acme AI", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 200
    assert res.json() == fake_briefing


def test_post_briefing_budget_exceeded_returns_429(client, monkeypatch):
    async def fake_run_pipeline(company, website, category, gl):
        raise BudgetExceeded("budget spent")

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    res = client.post(
        "/api/briefing",
        json={"company": "Acme AI", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 429


def test_post_briefing_validation_error_returns_422(client, monkeypatch):
    async def fake_run_pipeline(company, website, category, gl):
        raise ValidationError("bad input")

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    res = client.post(
        "/api/briefing",
        json={"company": "Acme AI", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 422


def test_get_briefings_empty_list(client):
    res = client.get("/api/briefings")
    assert res.status_code == 200
    assert res.json() == []


def test_get_briefings_lists_saved(client):
    storage.save_briefing({"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"})
    res = client.get("/api/briefings")
    assert res.status_code == 200
    assert res.json() == [{"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"}]


def test_get_briefing_by_id(client):
    storage.save_briefing({"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"})
    res = client.get("/api/briefings/x")
    assert res.status_code == 200
    assert res.json()["company"] == "Acme AI"


def test_get_briefing_by_id_not_found(client):
    res = client.get("/api/briefings/missing")
    assert res.status_code == 404


def test_get_usage(client):
    res = client.get("/api/usage")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"live_searches", "budget", "remainder", "replay_mode"}


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "PitchScout" in res.text


def test_replay_mode_returns_matching_briefing(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "true")
    client = TestClient(main.app)
    storage.save_briefing({"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"})
    res = client.post(
        "/api/briefing",
        json={"company": "acme ai", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 200
    assert res.json()["id"] == "x"


def test_replay_mode_returns_404_when_no_match(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "true")
    client = TestClient(main.app)
    res = client.post(
        "/api/briefing",
        json={"company": "Nonexistent Co", "website": "https://x.com", "category": "cat"},
    )
    assert res.status_code == 404


def _parse_sse(text):
    events = []
    for chunk in text.split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


def test_stream_briefing_emits_progress_then_briefing(client, monkeypatch):
    async def fake_steps(company, website, category, gl):
        yield {"progress": 10, "label": "Working"}
        yield {"progress": 100, "label": "Done", "briefing": {"id": "x", "company": company}}

    monkeypatch.setattr(main, "run_pipeline_steps", fake_steps)
    res = client.get(
        "/api/briefing/stream",
        params={"company": "Acme AI", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    assert res.status_code == 200
    events = _parse_sse(res.text)
    assert events[0] == {"progress": 10, "label": "Working"}
    assert events[-1]["briefing"]["company"] == "Acme AI"


def test_stream_briefing_budget_exceeded_emits_error_event(client, monkeypatch):
    async def fake_steps(company, website, category, gl):
        raise BudgetExceeded("budget spent")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(main, "run_pipeline_steps", fake_steps)
    res = client.get(
        "/api/briefing/stream",
        params={"company": "Acme AI", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    events = _parse_sse(res.text)
    assert events[-1] == {"error": True, "status": 429, "detail": "budget spent"}


def test_stream_briefing_validation_error_emits_error_event(client, monkeypatch):
    async def fake_steps(company, website, category, gl):
        raise ValidationError("bad input")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(main, "run_pipeline_steps", fake_steps)
    res = client.get(
        "/api/briefing/stream",
        params={"company": "", "website": "https://acme.ai", "category": "AI legal assistant"},
    )
    events = _parse_sse(res.text)
    assert events[-1] == {"error": True, "status": 422, "detail": "bad input"}


def test_stream_briefing_replay_mode_returns_matching_briefing(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "true")
    storage.save_briefing({"id": "x", "company": "Acme AI", "generated_at": "2026-01-01T00:00:00+00:00"})
    client = TestClient(main.app)
    res = client.get(
        "/api/briefing/stream",
        params={"company": "acme ai", "website": "https://acme.ai", "category": "cat"},
    )
    events = _parse_sse(res.text)
    assert events[-1]["briefing"]["id"] == "x"


def test_stream_briefing_replay_mode_no_match_emits_error_event(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "true")
    client = TestClient(main.app)
    res = client.get(
        "/api/briefing/stream",
        params={"company": "Nonexistent Co", "website": "https://x.com", "category": "cat"},
    )
    events = _parse_sse(res.text)
    assert events[-1]["error"] is True
    assert events[-1]["status"] == 404
