from app import validator
from app.prompts import DILIGENCE_AREAS, SCORECARD_DIMENSIONS


def make_evidence(id_, domain, title, engine="google"):
    return {
        "id": id_, "search_no": 1, "engine": engine, "title": title,
        "snippet": "", "url": f"https://{domain}/x", "source_domain": domain,
        "published_date": None, "retrieved_at": "2026-01-15T00:00:00+00:00", "stale": False,
    }


EVIDENCE_MAP = {
    "e01": make_evidence("e01", "techcrunch.com", "Acme AI raises $14M Series A"),
    "e02": make_evidence("e02", "venturebeat.com", "Northbridge backs Acme AI's $14M round"),
    "e03": make_evidence("e03", "acme.ai", "Acme AI pricing starts at $99/month"),
    "e04": make_evidence("e04", "techcrunch.com", "Unrelated TechCrunch article"),
    "e05": make_evidence("e05", "google.com", "Thomson Reuters Corp (TRI:NYSE)", engine="google_finance"),
}


def test_statement_with_invalid_evidence_id_is_dropped():
    statement = {"text": "Fabricated claim", "confidence": "Single source", "evidence": ["e99"]}
    assert validator.validate_statement(statement, EVIDENCE_MAP) is None


def test_statement_strips_invalid_ids_but_keeps_valid_ones():
    statement = {"text": "Acme AI raised funding", "confidence": "Single source", "evidence": ["e01", "e99"]}
    result = validator.validate_statement(statement, EVIDENCE_MAP)
    assert result is not None
    assert result["evidence"] == ["e01"]


def test_corroborated_requires_two_distinct_domains():
    assert validator.is_corroborated(["e01"], EVIDENCE_MAP) is False
    assert validator.is_corroborated(["e01", "e03"], EVIDENCE_MAP) is True


def test_corroborated_fails_on_near_duplicate_titles_same_pair():
    # e01 and e04 share a domain, so they can never corroborate each other regardless of title.
    assert validator.is_corroborated(["e01", "e04"], EVIDENCE_MAP) is False


def test_downgrades_corroborated_to_single_source_when_rule_fails():
    statement = {"text": "Acme AI raised $14M", "confidence": "Corroborated", "evidence": ["e01"]}
    result = validator.validate_statement(statement, EVIDENCE_MAP)
    assert result["confidence"] == "Single source"


def test_keeps_corroborated_when_rule_passes():
    statement = {"text": "Acme AI raised $14M", "confidence": "Corroborated", "evidence": ["e01", "e02"]}
    result = validator.validate_statement(statement, EVIDENCE_MAP)
    assert result["confidence"] == "Corroborated"


def test_validate_market_defaults_invalid_verdict_to_mixed():
    market = {"verdict": "bogus", "verdict_text": "x", "verdict_evidence": ["e01"], "points": []}
    result = validator.validate_market(market, EVIDENCE_MAP)
    assert result["verdict"] == "Mixed"


def test_validate_market_keeps_valid_verdict_and_filters_points():
    market = {
        "verdict": "Expanding",
        "verdict_text": "Rising interest",
        "verdict_evidence": ["e01", "e99"],
        "points": [{"text": "Trend up", "confidence": "Single source", "evidence": ["e01"]}],
    }
    result = validator.validate_market(market, EVIDENCE_MAP)
    assert result["verdict"] == "Expanding"
    assert result["verdict_evidence"] == ["e01"]
    assert len(result["points"]) == 1


def test_validate_risks_drops_items_with_no_valid_evidence():
    risks = [{"category": "legal", "text": "A lawsuit", "evidence": ["e99"]}]
    assert validator.validate_risks(risks, EVIDENCE_MAP) == []


def test_validate_risks_defaults_invalid_category_to_other():
    risks = [{"category": "bogus", "text": "Something risky", "evidence": ["e01"]}]
    result = validator.validate_risks(risks, EVIDENCE_MAP)
    assert result[0]["category"] == "other"


def test_validate_commercial_drops_empty_listed_comparables():
    commercial = {
        "pricing_comparison": [],
        "listed_comparables": [{"name": "X", "ticker": "X:NYSE", "price": "1", "market_cap": "1",
                                  "price_movement": "1", "evidence": []}],
        "mismatches": [],
    }
    result = validator.validate_commercial(commercial, EVIDENCE_MAP)
    assert result["listed_comparables"] == []


def test_validate_commercial_drops_listed_comparable_not_from_google_finance():
    # e03 is a plain "google" evidence item, not google_finance, so this must be dropped
    # even though it cites valid evidence — this is the "wrong competitor data in listed
    # comparables" bug class.
    commercial = {
        "pricing_comparison": [],
        "listed_comparables": [{"name": "LexBrief", "ticker": "Not reported", "price": "$49/month",
                                  "market_cap": "Not reported", "price_movement": "Not reported",
                                  "evidence": ["e03"]}],
        "mismatches": [],
    }
    result = validator.validate_commercial(commercial, EVIDENCE_MAP)
    assert result["listed_comparables"] == []


def test_validate_commercial_keeps_listed_comparables_with_evidence():
    commercial = {
        "pricing_comparison": [],
        "listed_comparables": [{"name": "Thomson Reuters", "ticker": "TRI:NYSE", "price": "1", "market_cap": "1",
                                  "price_movement": "1", "evidence": ["e05"]}],
        "mismatches": [],
    }
    result = validator.validate_commercial(commercial, EVIDENCE_MAP)
    assert len(result["listed_comparables"]) == 1


def test_validate_commercial_has_no_app_or_shopping_keys():
    result = validator.validate_commercial({}, EVIDENCE_MAP)
    assert set(result.keys()) == {"pricing_comparison", "listed_comparables", "mismatches"}


def _row(**kw):
    row = {
        "area": "Funding and investors",
        "topic": "Series A use of proceeds",
        "status": "Found",
        "found": "Raised $14M led by Northbridge.",
        "question": "How much of the round is already committed to headcount?",
        "why": "Burn shapes the next raise.",
        "priority": 1,
        "evidence": ["e01"],
    }
    row.update(kw)
    return row


def test_validate_diligence_keeps_found_row_with_valid_evidence():
    rows = validator.validate_diligence([_row()], EVIDENCE_MAP)
    assert len(rows) == 1
    assert rows[0]["status"] == "Found"
    assert rows[0]["found"] == "Raised $14M led by Northbridge."
    assert rows[0]["evidence"] == ["e01"]


def test_validate_diligence_downgrades_found_with_no_valid_evidence():
    # An uncited "Found" is the bug class where the briefing claims a finding it
    # cannot show, so the status drops and the unciteable sentence is replaced.
    rows = validator.validate_diligence([_row(evidence=["e99"])], EVIDENCE_MAP)
    assert rows[0]["status"] == "Missing"
    assert rows[0]["found"] == validator.NO_EVIDENCE_TEXT
    assert rows[0]["question"]  # the question is judgment, not a claim, so it survives


def test_validate_diligence_keeps_question_on_found_rows():
    rows = validator.validate_diligence([_row(status="Found")], EVIDENCE_MAP)
    assert rows[0]["question"]


def test_validate_diligence_ranks_priority_one_first():
    rows = validator.validate_diligence(
        [
            _row(topic="Third", priority=3, question="q3"),
            _row(topic="First", priority=1, question="q1"),
            _row(topic="Second", priority=2, question="q2"),
        ],
        EVIDENCE_MAP,
    )
    assert [r["topic"] for r in rows] == ["First", "Second", "Third"]


def test_validate_diligence_clamps_priority_and_status():
    rows = validator.validate_diligence(
        [_row(priority=9, status="bogus", question="q")], EVIDENCE_MAP
    )
    assert rows[0]["priority"] == 3
    assert rows[0]["status"] == "Missing"


def test_validate_diligence_defaults_unknown_area():
    rows = validator.validate_diligence([_row(area="Vibes")], EVIDENCE_MAP)
    assert rows[0]["area"] == validator.FALLBACK_AREA


def test_validate_diligence_accepts_every_declared_area():
    rows = validator.validate_diligence(
        [_row(area=area, question=f"q {area}") for area in DILIGENCE_AREAS], EVIDENCE_MAP
    )
    assert {r["area"] for r in rows} == set(DILIGENCE_AREAS)


def test_validate_diligence_dedupes_repeated_questions():
    rows = validator.validate_diligence(
        [_row(topic="A", question="Same question?"), _row(topic="B", question="same QUESTION?")],
        EVIDENCE_MAP,
    )
    assert len(rows) == 1


def test_validate_diligence_truncates_at_max_rows():
    rows = validator.validate_diligence(
        [_row(topic=f"T{i}", question=f"Q{i}?") for i in range(30)], EVIDENCE_MAP
    )
    assert len(rows) == validator.MAX_DILIGENCE_ROWS


def test_validate_key_facts_drops_uncited_facts():
    facts = [
        {"label": "Latest round", "value": "$14M Series A", "evidence": ["e01"]},
        {"label": "Headcount", "value": "400 staff", "evidence": ["e99"]},
    ]
    result = validator.validate_key_facts(facts, EVIDENCE_MAP)
    assert [f["label"] for f in result] == ["Latest round"]


def test_validate_news_sorts_newest_first_and_drops_unknown_ids():
    evidence_map = dict(EVIDENCE_MAP)
    evidence_map["e10"] = make_evidence("e10", "reuters.com", "Older item", engine="google_news")
    evidence_map["e10"]["published_date"] = "2026-01-02"
    evidence_map["e11"] = make_evidence("e11", "wsj.com", "Newer item", engine="google_news")
    evidence_map["e11"]["published_date"] = "2026-09-30"
    news = [
        {"evidence": ["e10"], "so_what": "Signals a slower quarter."},
        {"evidence": ["e99"], "so_what": "Fabricated."},
        {"evidence": ["e11"], "so_what": "Signals renewed momentum."},
    ]
    result = validator.validate_news(news, evidence_map)
    assert [h["evidence"][0] for h in result] == ["e11", "e10"]


def test_validate_news_drops_highlights_without_a_read():
    news = [{"evidence": ["e01"], "so_what": "  "}]
    assert validator.validate_news(news, EVIDENCE_MAP) == []


def test_validate_overview_survives_without_citations():
    overview = {"one_liner": "Acme AI is a legal research assistant.",
                "paragraph": "A longer paragraph.", "evidence": ["e99"]}
    result = validator.validate_overview(overview, EVIDENCE_MAP)
    assert result["paragraph"] == "A longer paragraph."
    assert result["evidence"] == []


def test_validate_trajectory_validates_signals():
    trajectory = {
        "headline": "Moving upmarket",
        "paragraph": "Forward read.",
        "signals": [{"text": "Hiring enterprise AEs", "confidence": "Inferred", "evidence": ["e01"]}],
    }
    result = validator.validate_trajectory(trajectory, EVIDENCE_MAP)
    assert result["headline"] == "Moving upmarket"
    assert len(result["signals"]) == 1


def test_validate_commercial_defaults_unknown_pricing_source():
    commercial = {
        "pricing_comparison": [
            {"name": "Acme", "lowest_paid_plan": "$99/mo", "free_tier": "Yes",
             "contact_sales_tier": "Yes", "pricing_source": "made up", "evidence": ["e03"]}
        ],
        "listed_comparables": [],
        "mismatches": [],
    }
    result = validator.validate_commercial(commercial, EVIDENCE_MAP)
    assert result["pricing_comparison"][0]["pricing_source"] == "Not found"


def test_validate_commercial_keeps_third_party_pricing_source():
    commercial = {
        "pricing_comparison": [
            {"name": "Acme", "lowest_paid_plan": "$60,000/year", "free_tier": "No",
             "contact_sales_tier": "Yes", "pricing_source": "Third party", "evidence": ["e03"]}
        ],
        "listed_comparables": [],
        "mismatches": [],
    }
    result = validator.validate_commercial(commercial, EVIDENCE_MAP)
    assert result["pricing_comparison"][0]["pricing_source"] == "Third party"
    assert result["pricing_comparison"][0]["lowest_paid_plan"] == "$60,000/year"


def test_validate_scorecard_always_has_a_score():
    scorecard = [{"dimension": "Team", "score": None, "rationale": "", "evidence": []}]
    result = validator.validate_scorecard(scorecard, EVIDENCE_MAP)
    team = next(s for s in result if s["dimension"] == "Team")
    assert team["score"] == 3
    assert team["rationale"]


def test_validate_scorecard_clamps_out_of_range_scores():
    scorecard = [{"dimension": "Team", "score": 9, "rationale": "x", "evidence": ["e01"]}]
    result = validator.validate_scorecard(scorecard, EVIDENCE_MAP)
    assert next(s for s in result if s["dimension"] == "Team")["score"] == 5


def test_validate_scorecard_covers_all_five_dimensions():
    result = validator.validate_scorecard([], EVIDENCE_MAP)
    assert {s["dimension"] for s in result} == set(SCORECARD_DIMENSIONS)
    assert all(s["score"] is not None for s in result)


def test_validate_output_end_to_end_shape():
    analysis = {
        "overview": {"one_liner": "Acme AI is a legal research assistant.",
                     "paragraph": "Longer prose.", "evidence": ["e01"]},
        "key_facts": [{"label": "Latest round", "value": "$14M Series A", "evidence": ["e01"]}],
        "market": {"verdict": "Expanding", "verdict_text": "x", "verdict_evidence": ["e01"], "points": []},
        "competitors": [],
        "news_highlights": [],
        "trajectory": {"headline": "Upmarket", "paragraph": "Forward read.", "signals": []},
        "risks": [],
        "commercial": {
            "pricing_comparison": [],
            "listed_comparables": [],
            "mismatches": [],
        },
        "diligence": [_row()],
        "scorecard": [],
    }
    result = validator.validate_output(analysis, EVIDENCE_MAP)
    assert set(result.keys()) == {
        "overview", "key_facts", "market", "competitors", "news_highlights",
        "trajectory", "risks", "commercial", "diligence", "scorecard",
    }
    assert len(result["scorecard"]) == 5
    assert all(s["score"] is not None for s in result["scorecard"])
    assert len(result["diligence"]) == 1


def test_validate_output_tolerates_a_missing_analysis():
    """Every section has to degrade to an empty shape rather than raise."""
    result = validator.validate_output({}, EVIDENCE_MAP)
    assert result["diligence"] == []
    assert result["overview"]["paragraph"] == ""
    assert len(result["scorecard"]) == 5
