"""The ten pipeline steps, run in order, for one briefing request."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from . import analyzer, planner, roles, series, storage, validator
from .evidence import IdCounter
from .normalizers import normalize
from .serp_client import SerpResponse, search
from .validator import is_corroborated


class ValidationError(Exception):
    """Raised when a required input field is missing or blank."""


def validate_inputs(company: str, website: str, category: str) -> None:
    missing = [
        name
        for name, value in (("company", company), ("website", website), ("category", category))
        if not value or not value.strip()
    ]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def _stock_subject(
    company: str, entities: dict[str, Any], listed_companies: list[dict[str, Any]]
) -> dict[str, Any]:
    """Picks whose share price heads the briefing.

    The company's own listing when it has one. When it does not, the best listed
    comparable stands in — a private company has no share price, and an empty
    chart says less than a named peer's does, provided the panel is plain about
    whose line it is drawing.
    """
    own = str(entities.get("subject_ticker") or "").strip()
    if own:
        return {"ticker": own, "is_subject": True, "stands_in_for": ""}
    for listed in listed_companies:
        ticker = str(listed.get("ticker") or "").strip()
        if ticker:
            return {"ticker": ticker, "is_subject": False, "stands_in_for": company}
    return {"ticker": "", "is_subject": False, "stands_in_for": ""}


async def _run_one(planned: planner.PlannedSearch) -> tuple[planner.PlannedSearch, SerpResponse, datetime]:
    response = await search(planned.engine, planned.params)
    return planned, response, datetime.now(timezone.utc)


async def _run_wave(
    planned_searches: list[planner.PlannedSearch],
    id_counter: IdCounter,
    company: str,
    website: str,
    category: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, SerpResponse]]:
    """Runs a wave of searches concurrently. Returns (evidence, search_log, raw_by_search_no)."""
    results = await asyncio.gather(*[_run_one(p) for p in planned_searches])

    evidence: list[dict[str, Any]] = []
    search_log: list[dict[str, Any]] = []
    raw_by_no: dict[int, SerpResponse] = {}

    for planned, response, retrieved_at in results:
        raw_by_no[planned.no] = response
        items = (
            []
            if response.status == "error"
            else normalize(
                response.raw, planned.no, planned.engine, retrieved_at, id_counter, company, website, category
            )
        )
        evidence.extend(items)

        if response.status == "error":
            status = "error"
        elif not items:
            status = "empty"
        else:
            status = response.status

        search_log.append(
            {
                "number": planned.no,
                "engine": planned.engine,
                "query": planned.params.get("q", ""),
                "status": status,
                "result_count": len(items),
            }
        )

    return evidence, search_log, raw_by_no


def _hiring_signal(job_evidence: list[dict[str, Any]], evidence_map: dict[str, dict]) -> dict[str, Any] | None:
    """Builds the code-computed role-mix signal shown in the briefing.

    The same numbers are handed to the analysis call as settled fact (see
    `role_mix_note`), so the model reasons from them instead of re-deriving the mix
    from truncated job snippets and contradicting the figure on screen.
    """
    if not job_evidence:
        return None
    titles = [item["title"] for item in job_evidence]
    counts = roles.role_mix(titles)
    total = len(titles)
    ml_share = counts["ML and research"] / total if total else 0.0
    text = (
        f"{total} open role(s) found. Role mix — Engineering: {counts['Engineering']}, "
        f"ML and research: {counts['ML and research']} ({ml_share:.0%}), "
        f"Sales and marketing: {counts['Sales and marketing']}, Other: {counts['Other']}."
    )
    evidence_ids = [item["id"] for item in job_evidence]
    confidence = "Corroborated" if is_corroborated(evidence_ids, evidence_map) else "Single source"
    return {
        "text": text,
        "confidence": confidence,
        "evidence": evidence_ids,
        "total_roles": total,
        "counts": counts,
        "ml_share": round(ml_share, 3),
        "titles": titles[:8],
    }


def role_mix_note(hiring: dict[str, Any] | None) -> str | None:
    """Phrases the computed role mix for the analysis prompt."""
    if hiring is None:
        return None
    counts = hiring["counts"]
    cited = ", ".join(hiring["evidence"])
    return (
        f"- Open roles found for this company: {hiring['total_roles']} "
        f"(evidence {cited}).\n"
        f"- Role mix, classified in code from the job titles: "
        f"Engineering {counts['Engineering']}, ML and research {counts['ML and research']}, "
        f"Sales and marketing {counts['Sales and marketing']}, Other {counts['Other']}.\n"
        f"- ML and research share of open roles: {hiring['ml_share']:.0%}.\n"
        f"- Treat the presence or absence of ML/research roles as answered by these numbers; "
        f"do not mark it unknown, and do not ask the founders whether such roles exist."
    )


async def run_pipeline_steps(company: str, website: str, category: str, gl: str = "us") -> AsyncIterator[dict[str, Any]]:
    """Runs all ten steps, yielding progress events along the way.

    Every yielded event has `progress` (0-100) and `label`. The final event also carries
    `briefing`, the saved briefing JSON. A caller that only wants the end result can drain
    this generator and keep the last event's `briefing` — see run_pipeline below.
    """
    # Step 1: validate
    validate_inputs(company, website, category)
    yield {"progress": 2, "label": "Validating input"}

    id_counter = IdCounter()

    # Steps 2-3: wave 1
    yield {"progress": 5, "label": "Running 11 searches"}
    wave1_searches = planner.plan_wave_1(company, website, category, gl)
    wave1_evidence, wave1_log, wave1_raw = await _run_wave(wave1_searches, id_counter, company, website, category)
    yield {"progress": 35, "label": "Reading the evidence"}

    # Step 4: entity call
    yield {"progress": 38, "label": "Identifying competitors"}
    entities = await analyzer.call_entities(company, website, category, wave1_evidence)
    competitors = entities.get("competitors", [])[:3]
    listed_companies = entities.get("listed_companies", [])[:2]
    subject = _stock_subject(company, entities, listed_companies)

    # Steps 5-6: wave 2
    yield {"progress": 48, "label": "Running 7 more searches"}
    wave2_searches = planner.plan_wave_2(company, category, competitors, subject["ticker"], gl)
    wave2_evidence, wave2_log, wave2_raw = await _run_wave(wave2_searches, id_counter, company, website, category)

    # The trends timeline and the price graph only exist in the raw responses —
    # the normalizers reduce both to a sentence — so they are pulled out here.
    chart_series = series.build_series(
        {**wave1_raw, **wave2_raw}, company, category, planner.STOCK_WINDOW, subject
    )

    all_evidence = wave1_evidence + wave2_evidence
    evidence_map = {item["id"]: item for item in all_evidence}
    search_log = sorted(wave1_log + wave2_log, key=lambda s: s["number"])

    # Step 7: role mix (code, from search 8's evidence), handed to the analysis call as fact
    job_evidence = [item for item in wave1_evidence if item["search_no"] == 8]
    hiring = _hiring_signal(job_evidence, evidence_map)

    # Step 8: analysis call
    yield {"progress": 62, "label": "Analyzing the evidence"}
    analysis = await analyzer.call_analysis(
        company, website, category, all_evidence, role_mix_note(hiring)
    )
    yield {"progress": 90, "label": "Validating findings"}

    # Step 9: validate output
    validated = validator.validate_output(analysis, evidence_map)

    briefing = {
        "id": str(uuid.uuid4()),
        "company": company,
        "website": website,
        "category": category,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "searches": search_log,
        "series": chart_series,
        "overview": validated["overview"],
        "key_facts": validated["key_facts"],
        "hiring": hiring,
        "market": validated["market"],
        "market_position": validated["market_position"],
        "competitors": validated["competitors"],
        "news_highlights": validated["news_highlights"],
        "trajectory": validated["trajectory"],
        "risks": validated["risks"],
        "commercial": validated["commercial"],
        "scorecard": validated["scorecard"],
        "diligence": validated["diligence"],
        "evidence": evidence_map,
    }

    # Step 10: save
    yield {"progress": 97, "label": "Saving briefing"}
    storage.save_briefing(briefing)
    yield {"progress": 100, "label": "Done", "briefing": briefing}


async def run_pipeline(company: str, website: str, category: str, gl: str = "us") -> dict[str, Any]:
    """Runs all ten steps and returns the saved briefing, discarding progress events."""
    briefing: dict[str, Any] | None = None
    async for event in run_pipeline_steps(company, website, category, gl):
        if "briefing" in event:
            briefing = event["briefing"]
    return briefing
