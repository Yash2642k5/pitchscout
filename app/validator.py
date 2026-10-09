"""Validates and repairs the analysis call's output.

Three jobs, matching pipeline step 9:
  - citation check: drop any evidence ID that is not in the evidence map;
    drop a statement entirely if nothing valid remains
  - confidence rules: downgrade any Corroborated statement that fails the
    two-domain, non-duplicate-title rule to Single source; every scorecard
    dimension always carries a 1-5 score
  - diligence rows: a Found/Partial status has to be backed by a surviving
    citation, rows are ranked by priority, and questions are de-duplicated

The diligence list carries both findings and questions, so there is no
separate question-assembly step: what the analyst asks lives on the same row
as what the evidence already established.
"""

from difflib import SequenceMatcher
from typing import Any

from .prompts import (
    DILIGENCE_AREAS,
    DILIGENCE_STATUSES,
    MARKET_VERDICTS,
    RISK_CATEGORIES,
    SCORECARD_DIMENSIONS,
)

SIMILARITY_THRESHOLD = 0.8
MAX_DILIGENCE_ROWS = 14
MAX_NEWS_HIGHLIGHTS = 6
NO_EVIDENCE_TEXT = "Nothing in the evidence."
FALLBACK_AREA = "Other"

_AREA_ORDER = {area: i for i, area in enumerate(DILIGENCE_AREAS)}


def _filter_ids(ids: list[str], evidence_map: dict[str, dict]) -> list[str]:
    seen = set()
    out = []
    for i in ids or []:
        if i in evidence_map and i not in seen:
            out.append(i)
            seen.add(i)
    return out


def is_corroborated(ids: list[str], evidence_map: dict[str, dict]) -> bool:
    domains_titles = [
        (evidence_map[i]["source_domain"], evidence_map[i]["title"]) for i in ids
    ]
    distinct_domains = {d for d, _ in domains_titles}
    if len(distinct_domains) < 2:
        return False
    for i, (domain_a, title_a) in enumerate(domains_titles):
        for domain_b, title_b in domains_titles[i + 1 :]:
            if domain_a == domain_b:
                continue
            similarity = SequenceMatcher(None, title_a or "", title_b or "").ratio()
            if similarity < SIMILARITY_THRESHOLD:
                return True
    return False


def validate_statement(statement: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any] | None:
    """Filters evidence IDs and enforces the confidence rule. Returns None if dropped."""
    valid_ids = _filter_ids(statement.get("evidence", []), evidence_map)
    if not valid_ids:
        return None
    confidence = statement.get("confidence", "Single source")
    if confidence == "Corroborated" and not is_corroborated(valid_ids, evidence_map):
        confidence = "Single source"
    return {"text": statement.get("text", ""), "confidence": confidence, "evidence": valid_ids}


def validate_section(statements: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    out = []
    for s in statements or []:
        # Some models return plain strings instead of statement objects — coerce them.
        if isinstance(s, str):
            s = {"text": s, "confidence": "Single source", "evidence": []}
        validated = validate_statement(s, evidence_map)
        # Allow statements with no valid evidence IDs if they at least have text
        # (e.g. competitor descriptions that don't cite a specific evidence item).
        if validated is None and s.get("text"):
            out.append({"text": s["text"], "confidence": "Single source", "evidence": []})
        elif validated is not None:
            out.append(validated)
    return out


def validate_overview(overview: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    """The opening paragraph. Kept even when uncited — it synthesises the whole evidence set."""
    overview = overview or {}
    if isinstance(overview, str):
        overview = {"paragraph": overview}
    return {
        "one_liner": overview.get("one_liner", ""),
        "paragraph": overview.get("paragraph", ""),
        "evidence": _filter_ids(overview.get("evidence", []), evidence_map),
    }


def validate_key_facts(key_facts: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    """Each fact is a factual claim, so an uncited one is dropped."""
    out = []
    for fact in key_facts or []:
        if not isinstance(fact, dict):
            continue
        valid_ids = _filter_ids(fact.get("evidence", []), evidence_map)
        label = (fact.get("label") or "").strip()
        value = (fact.get("value") or "").strip()
        if not valid_ids or not label or not value:
            continue
        out.append({"label": label, "value": value, "evidence": valid_ids})
    return out


def validate_market(market: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    market = market or {}
    verdict = market.get("verdict")
    if verdict not in MARKET_VERDICTS:
        verdict = "Mixed"
    return {
        "verdict": verdict,
        "verdict_text": market.get("verdict_text", ""),
        "verdict_evidence": _filter_ids(market.get("verdict_evidence", []), evidence_map),
        "points": validate_section(market.get("points", []), evidence_map),
    }


def _published_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    """Newest first; undated items sort last."""
    date = item.get("published_date") or ""
    return (0 if date else 1, _invert_date(date))


def _invert_date(date: str) -> str:
    # Descending sort on an ascending key: invert each digit so "2026" < "2025".
    return "".join(str(9 - int(c)) if c.isdigit() else c for c in date)


def validate_news(news: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    """Resolves each highlight to one real evidence item and re-sorts newest first.

    Ordering is enforced here rather than trusted from the model: the evidence map
    already carries parsed dates, so the code can simply sort on them.
    """
    out = []
    seen: set[str] = set()
    for item in news or []:
        if not isinstance(item, dict):
            continue
        valid_ids = _filter_ids(item.get("evidence", []), evidence_map)
        so_what = (item.get("so_what") or "").strip()
        if not valid_ids or not so_what:
            continue
        evidence_id = valid_ids[0]
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        out.append({"evidence": [evidence_id], "so_what": so_what})
    out.sort(key=lambda h: _published_sort_key(evidence_map[h["evidence"][0]]))
    return out[:MAX_NEWS_HIGHLIGHTS]


def validate_trajectory(trajectory: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    trajectory = trajectory or {}
    if isinstance(trajectory, str):
        trajectory = {"paragraph": trajectory}
    return {
        "headline": trajectory.get("headline", ""),
        "paragraph": trajectory.get("paragraph", ""),
        "signals": validate_section(trajectory.get("signals", []), evidence_map),
    }


def validate_risks(risks: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    out = []
    for r in risks or []:
        valid_ids = _filter_ids(r.get("evidence", []), evidence_map)
        if not valid_ids:
            continue
        category = r.get("category")
        if category not in RISK_CATEGORIES:
            category = "other"
        out.append({"category": category, "text": r.get("text", ""), "evidence": valid_ids})
    return out


def validate_commercial(commercial: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    commercial = commercial or {}

    pricing_rows = []
    for row in (commercial.get("pricing_comparison") or [])[:4]:
        valid_ids = _filter_ids(row.get("evidence", []), evidence_map)
        source = row.get("pricing_source", "Not found")
        if source not in ("Vendor page", "Third party", "Not found"):
            source = "Not found"
        pricing_rows.append(
            {
                "name": row.get("name", ""),
                "lowest_paid_plan": row.get("lowest_paid_plan", "Not found"),
                "free_tier": row.get("free_tier", "Not found"),
                "contact_sales_tier": row.get("contact_sales_tier", "Not found"),
                "pricing_source": source,
                "evidence": valid_ids,
            }
        )

    comparables = []
    for row in (commercial.get("listed_comparables") or [])[:2]:
        valid_ids = _filter_ids(row.get("evidence", []), evidence_map)
        # A listed comparable is only genuine if every citation actually comes from
        # google_finance evidence — this catches the model mislabeling a competitor's
        # pricing-page row as a public-market comparable.
        valid_ids = [i for i in valid_ids if evidence_map[i].get("engine") == "google_finance"]
        if not valid_ids:
            continue
        comparables.append(
            {
                "name": row.get("name", ""),
                "ticker": row.get("ticker", ""),
                "price": row.get("price", "Not reported"),
                "market_cap": row.get("market_cap", "Not reported"),
                "price_movement": row.get("price_movement", "Not reported"),
                "evidence": valid_ids,
            }
        )

    mismatches = []
    for m in commercial.get("mismatches") or []:
        valid_ids = _filter_ids(m.get("evidence", []), evidence_map)
        if not valid_ids:
            continue
        mismatches.append(
            {
                "rule": m.get("rule", ""),
                "claim": m.get("claim", ""),
                "pricing_note": m.get("pricing_note", ""),
                "why_it_matters": m.get("why_it_matters", ""),
                "question": m.get("question", ""),
                "evidence": valid_ids,
            }
        )

    return {
        "pricing_comparison": pricing_rows,
        "listed_comparables": comparables,
        "mismatches": mismatches,
    }


def _clamp_priority(value: Any) -> int:
    try:
        return max(1, min(3, int(value)))
    except (TypeError, ValueError):
        return 2


def validate_diligence(diligence: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    """Validates the merged findings-and-questions list.

    A Found or Partial status is a claim about the evidence, so it only survives with a
    citation that survived; without one the row falls back to Missing and its `found`
    sentence is replaced rather than shown uncited. The question and why are the model's
    own judgment rather than factual claims, so they are kept either way.
    """
    rows = []
    seen_questions: set[str] = set()
    for row in diligence or []:
        if not isinstance(row, dict):
            continue
        topic = (row.get("topic") or "").strip()
        question = (row.get("question") or "").strip()
        if not topic and not question:
            continue

        valid_ids = _filter_ids(row.get("evidence", []), evidence_map)
        status = row.get("status")
        if status not in DILIGENCE_STATUSES:
            status = "Missing"
        found = (row.get("found") or "").strip()
        if not valid_ids:
            status = "Missing"
            found = NO_EVIDENCE_TEXT
        elif not found:
            found = NO_EVIDENCE_TEXT

        key = question.lower()
        if key and key in seen_questions:
            continue
        if key:
            seen_questions.add(key)

        area = row.get("area")
        if area not in _AREA_ORDER:
            area = FALLBACK_AREA

        rows.append(
            {
                "area": area,
                "topic": topic,
                "status": status,
                "found": found,
                "question": question,
                "why": (row.get("why") or "").strip(),
                "priority": _clamp_priority(row.get("priority")),
                "evidence": valid_ids,
            }
        )

    # Priority first so the meeting-critical questions sit at the top, then the fixed
    # area order so repeat runs of the same company stay comparable row for row.
    rows.sort(key=lambda r: (r["priority"], _AREA_ORDER.get(r["area"], len(_AREA_ORDER))))
    return rows[:MAX_DILIGENCE_ROWS]


def validate_scorecard(scorecard: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    by_dim = {s.get("dimension"): s for s in scorecard or []}
    out = []
    for dim in SCORECARD_DIMENSIONS:
        s = by_dim.get(dim, {})
        valid_ids = _filter_ids(s.get("evidence", []), evidence_map)
        try:
            score = max(1, min(5, int(s.get("score"))))
        except (TypeError, ValueError):
            score = 3
        rationale = s.get("rationale") or "Limited evidence; estimated from category norms."
        out.append({"dimension": dim, "score": score, "rationale": rationale, "evidence": valid_ids})
    return out


def validate_output(analysis: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    """Runs the full validation pass and returns the briefing-ready structure."""
    return {
        "overview": validate_overview(analysis.get("overview", {}), evidence_map),
        "key_facts": validate_key_facts(analysis.get("key_facts", []), evidence_map),
        "market": validate_market(analysis.get("market", {}), evidence_map),
        "competitors": validate_section(analysis.get("competitors", []), evidence_map),
        "news_highlights": validate_news(analysis.get("news_highlights", []), evidence_map),
        "trajectory": validate_trajectory(analysis.get("trajectory", {}), evidence_map),
        "risks": validate_risks(analysis.get("risks", []), evidence_map),
        "commercial": validate_commercial(analysis.get("commercial", {}), evidence_map),
        "diligence": validate_diligence(analysis.get("diligence", []), evidence_map),
        "scorecard": validate_scorecard(analysis.get("scorecard", []), evidence_map),
    }
