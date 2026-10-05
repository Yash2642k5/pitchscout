"""Validates and repairs the analysis call's output.

Three jobs, matching pipeline step 9:
  - citation check: drop any evidence ID that is not in the evidence map;
    drop a statement entirely if nothing valid remains
  - confidence rules: downgrade any Corroborated statement that fails the
    two-domain, non-duplicate-title rule to Single source; every scorecard
    dimension always carries a 1-5 score
  - question count: assemble the final 10-15 ranked questions in order
    (mismatch, then gap by priority, then risk) and truncate at 15
"""

from difflib import SequenceMatcher
from typing import Any

from .prompts import GAP_ITEMS, MARKET_VERDICTS, RISK_CATEGORIES, SCORECARD_DIMENSIONS

SIMILARITY_THRESHOLD = 0.8
MIN_QUESTIONS = 10
MAX_QUESTIONS = 15


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
        validated = validate_statement(s, evidence_map)
        if validated is not None:
            out.append(validated)
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
        pricing_rows.append(
            {
                "name": row.get("name", ""),
                "lowest_paid_plan": row.get("lowest_paid_plan", "Not found"),
                "free_tier": row.get("free_tier", "Not found"),
                "contact_sales_tier": row.get("contact_sales_tier", "Not found"),
                "evidence": _filter_ids(row.get("evidence", []), evidence_map),
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


def validate_gaps(gaps: list[dict], evidence_map: dict[str, dict]) -> list[dict]:
    by_no = {g.get("no"): g for g in gaps or []}
    out = []
    for item in GAP_ITEMS:
        g = by_no.get(item["no"], {})
        valid_ids = _filter_ids(g.get("evidence", []), evidence_map)
        status = g.get("status", "Missing")
        if status == "Found" and not valid_ids:
            status = "Missing"
        if status not in ("Found", "Partial", "Missing"):
            status = "Missing"
        out.append(
            {
                "no": item["no"],
                "item": item["item"],
                "priority": item["priority"],
                "status": status,
                "evidence": valid_ids,
                "question": g.get("question", ""),
                "why": g.get("why", ""),
            }
        )
    return out


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


def build_questions(
    commercial: dict[str, Any], gaps: list[dict], risk_questions: list[dict]
) -> list[dict]:
    questions: list[dict] = []

    for m in commercial.get("mismatches", []):
        if m.get("question"):
            questions.append(
                {"text": m["question"], "why": m.get("why_it_matters", ""), "priority": None, "source": "mismatch"}
            )

    gap_questions = [g for g in gaps if g["status"] != "Found" and g.get("question")]
    gap_questions.sort(key=lambda g: (g["priority"], g["no"]))
    for g in gap_questions:
        questions.append(
            {"text": g["question"], "why": g.get("why", ""), "priority": g["priority"], "source": "gap"}
        )

    for rq in risk_questions or []:
        text = rq.get("text") if isinstance(rq, dict) else rq
        why = rq.get("why", "") if isinstance(rq, dict) else ""
        if text:
            questions.append({"text": text, "why": why, "priority": None, "source": "risk"})

    # De-duplicate while preserving order.
    seen_text = set()
    deduped = []
    for q in questions:
        key = q["text"].strip().lower()
        if key and key not in seen_text:
            seen_text.add(key)
            deduped.append(q)

    return deduped[:MAX_QUESTIONS]


def validate_output(analysis: dict[str, Any], evidence_map: dict[str, dict]) -> dict[str, Any]:
    """Runs the full validation pass and returns the briefing-ready structure."""
    commercial = validate_commercial(analysis.get("commercial", {}), evidence_map)
    gaps = validate_gaps(analysis.get("gaps", []), evidence_map)
    questions = build_questions(commercial, gaps, analysis.get("risk_questions", []))

    return {
        "company_summary": validate_section(analysis.get("company_summary", []), evidence_map),
        "market": validate_market(analysis.get("market", {}), evidence_map),
        "competitors": validate_section(analysis.get("competitors", []), evidence_map),
        "risks": validate_risks(analysis.get("risks", []), evidence_map),
        "commercial": commercial,
        "gaps": gaps,
        "questions": questions,
        "scorecard": validate_scorecard(analysis.get("scorecard", []), evidence_map),
    }
