from app import validator
from app.prompts import GAP_ITEMS, SCORECARD_DIMENSIONS


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


def test_validate_gaps_merges_fixed_metadata():
    llm_gaps = [{"no": 3, "status": "Found", "evidence": ["e01"], "question": "", "why": ""}]
    gaps = validator.validate_gaps(llm_gaps, EVIDENCE_MAP)
    assert len(gaps) == 14
    item3 = next(g for g in gaps if g["no"] == 3)
    assert item3["item"] == "Funding round and amount"
    assert item3["priority"] == 1
    assert item3["status"] == "Found"
    missing_item = next(g for g in gaps if g["no"] == 1)
    assert missing_item["status"] == "Missing"


def test_validate_gaps_downgrades_found_with_no_valid_evidence():
    llm_gaps = [{"no": 3, "status": "Found", "evidence": ["e99"], "question": "q", "why": "w"}]
    gaps = validator.validate_gaps(llm_gaps, EVIDENCE_MAP)
    item3 = next(g for g in gaps if g["no"] == 3)
    assert item3["status"] == "Missing"


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


def test_build_questions_orders_mismatch_then_gap_then_risk():
    commercial = {"mismatches": [{"question": "Mismatch question?", "why_it_matters": "It matters."}]}
    gaps = [
        {"no": 3, "item": "Funding round and amount", "priority": 1, "status": "Missing",
         "question": "Gap Q priority 1", "why": "why1"},
        {"no": 1, "item": "Founder names", "priority": 3, "status": "Partial",
         "question": "Gap Q priority 3", "why": "why3"},
        {"no": 9, "item": "Public pricing", "priority": 1, "status": "Found",
         "question": "Should not appear", "why": ""},
    ]
    risk_questions = [{"text": "Risk question A", "why": "rwa"}, {"text": "Risk question B", "why": "rwb"}]
    questions = validator.build_questions(commercial, gaps, risk_questions)
    texts = [q["text"] for q in questions]
    assert texts[0] == "Mismatch question?"
    assert questions[0]["why"] == "It matters."
    assert "Gap Q priority 1" in texts
    assert texts.index("Gap Q priority 1") < texts.index("Gap Q priority 3")
    assert "Should not appear" not in texts
    assert texts[-2:] == ["Risk question A", "Risk question B"]
    assert questions[-1]["why"] == "rwb"


def test_build_questions_truncates_at_15():
    commercial = {"mismatches": []}
    gaps = [
        {"no": g["no"], "item": g["item"], "priority": g["priority"], "status": "Missing",
         "question": f"Q{g['no']}", "why": "w"}
        for g in GAP_ITEMS
    ]
    risk_questions = [{"text": f"R{i}", "why": "w"} for i in range(5)]
    questions = validator.build_questions(commercial, gaps, risk_questions)
    assert len(questions) == 15


def test_validate_output_end_to_end_shape():
    analysis = {
        "company_summary": [{"text": "Acme AI raised funding", "confidence": "Single source", "evidence": ["e01"]}],
        "market": {"verdict": "Expanding", "verdict_text": "x", "verdict_evidence": ["e01"], "points": []},
        "competitors": [],
        "risks": [],
        "commercial": {
            "pricing_comparison": [],
            "listed_comparables": [],
            "mismatches": [],
        },
        "gaps": [],
        "risk_questions": [{"text": "Risk Q", "why": "w"}],
        "scorecard": [],
    }
    result = validator.validate_output(analysis, EVIDENCE_MAP)
    assert set(result.keys()) == {
        "company_summary", "market", "competitors", "risks",
        "commercial", "gaps", "questions", "scorecard",
    }
    assert len(result["gaps"]) == 14
    assert len(result["scorecard"]) == 5
    assert all(s["score"] is not None for s in result["scorecard"])
