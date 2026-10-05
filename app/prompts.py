"""Prompts and output JSON schemas for both LLM calls.

Call 1 (entity call) proposes competitors and listed comparables from wave 1
evidence. Call 2 (analysis call) reasons over all evidence and returns the
company summary, market read, competitors, risks, the Commercial Reality
Check, gaps, questions, and the scorecard, as one JSON object shaped by
ANALYSIS_TOOL's input_schema. Both calls are forced into that shape through
tool use.
"""

from typing import Any

GOVERNING_RULE = (
    "You are an analyst assistant. You may use ONLY the evidence items given to you. "
    "Every statement you write must cite the evidence IDs (e.g. \"e03\") that support it. "
    "Never invent a fact, a number, a name, or a URL that is not present in the evidence. "
    "If the evidence does not support a claim, do not make the claim."
)

# The 14 fixed gap-checklist items. Names and priorities are settled; the
# LLM only supplies status and evidence for each, keyed by `no`.
GAP_ITEMS: list[dict[str, Any]] = [
    {"no": 1, "item": "Founder names", "priority": 3},
    {"no": 2, "item": "Founder prior experience", "priority": 2},
    {"no": 3, "item": "Funding round and amount", "priority": 1},
    {"no": 4, "item": "Named investors", "priority": 2},
    {"no": 5, "item": "Named paying customers", "priority": 1},
    {"no": 6, "item": "Product description from a non-company domain", "priority": 2},
    {"no": 7, "item": "ML or research roles among open jobs", "priority": 1},
    {"no": 8, "item": "At least one open role", "priority": 3},
    {"no": 9, "item": "Public pricing for the company", "priority": 1},
    {"no": 10, "item": "Pricing for all three competitors", "priority": 2},
    {"no": 11, "item": "Data returned for both listed companies", "priority": 3},
    {"no": 12, "item": "Category interest trend", "priority": 3},
    {"no": 13, "item": "Press coverage in the last 12 months", "priority": 2},
    {"no": 14, "item": "App or shopping listing", "priority": 3},
]

SCORECARD_DIMENSIONS = ["Team", "Traction", "Market", "Defensibility", "Risk"]

MISMATCH_RULES = ["positioning_gap", "free_tier_gap", "hidden_pricing", "bundling_threat"]

MARKET_VERDICTS = ["Expanding", "Saturated", "Mixed", "Nascent"]

RISK_CATEGORIES = ["legal", "regulatory", "founder_history", "reputational", "competitive", "other"]

_STATEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["Corroborated", "Single source", "Inferred"],
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "confidence", "evidence"],
}

_MARKET_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": MARKET_VERDICTS,
            "description": "Is this market saturated, expanding, mixed, or still nascent?",
        },
        "verdict_text": {
            "type": "string",
            "description": "One sentence justifying the verdict.",
        },
        "verdict_evidence": {"type": "array", "items": {"type": "string"}},
        "points": {
            "type": "array",
            "items": _STATEMENT_SCHEMA,
            "description": (
                "2-4 grounded points: interest trend direction, company interest vs. category "
                "interest, competitive density, category news. Each should help answer whether "
                "this market is getting more crowded or still has room."
            ),
        },
    },
    "required": ["verdict", "verdict_text", "verdict_evidence", "points"],
}

_RISK_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": RISK_CATEGORIES},
        "text": {
            "type": "string",
            "description": "One sentence covering the finding — a lawsuit, regulatory action, "
            "a founder's earlier failed startup, a complaint, or similar.",
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "text", "evidence"],
}

_GAP_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "no": {"type": "integer"},
        "status": {"type": "string", "enum": ["Found", "Partial", "Missing"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "question": {
            "type": "string",
            "description": "A question to ask the founders, used only if status is Partial or Missing.",
        },
        "why": {
            "type": "string",
            "description": "One short clause on why this question matters, used only if status "
            "is Partial or Missing.",
        },
    },
    "required": ["no", "status", "evidence", "question", "why"],
}

_PRICING_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "lowest_paid_plan": {"type": "string", "description": "'Not found' if absent"},
        "free_tier": {"type": "string", "description": "'Yes', 'No', or 'Not found'"},
        "contact_sales_tier": {"type": "string", "description": "'Yes', 'No', or 'Not found'"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "lowest_paid_plan", "free_tier", "contact_sales_tier", "evidence"],
}

_LISTED_COMPARABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "ticker": {"type": "string"},
        "price": {"type": "string", "description": "'Not reported' if absent"},
        "market_cap": {"type": "string", "description": "'Not reported' if absent"},
        "price_movement": {"type": "string", "description": "'Not reported' if absent"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "ticker", "price", "market_cap", "price_movement", "evidence"],
}

_MISMATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "rule": {"type": "string", "enum": MISMATCH_RULES},
        "claim": {"type": "string"},
        "pricing_note": {
            "type": "string",
            "description": (
                "One plain-text sentence describing what the pricing pages show, e.g. "
                "'Company lists no public plan; competitors start at $49/month.' "
                "This is prose, NOT a list of evidence IDs — those go in `evidence`."
            ),
        },
        "why_it_matters": {"type": "string"},
        "question": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rule", "claim", "pricing_note", "why_it_matters", "question", "evidence"],
}

_SCORECARD_DIM_SCHEMA = {
    "type": "object",
    "properties": {
        "dimension": {"type": "string", "enum": SCORECARD_DIMENSIONS},
        "score": {
            "type": "integer",
            "description": "Always an integer 1-5, even on thin evidence — give your best "
            "grounded estimate and flag low confidence in the rationale rather than skipping it.",
        },
        "rationale": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["dimension", "score", "rationale", "evidence"],
}

_RISK_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "why": {"type": "string", "description": "One short clause on why this matters."},
    },
    "required": ["text", "why"],
}

ENTITY_TOOL = {
    "name": "submit_entities",
    "description": "Submit the three competitors and any publicly listed comparable companies.",
    "input_schema": {
        "type": "object",
        "properties": {
            "competitors": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "domain": {"type": "string"},
                    },
                    "required": ["name", "domain"],
                },
            },
            "listed_companies": {
                "type": "array",
                "minItems": 0,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "ticker": {
                            "type": "string",
                            "description": "Formatted TICKER:EXCHANGE, e.g. MSFT:NASDAQ",
                        },
                    },
                    "required": ["name", "ticker"],
                },
            },
        },
        "required": ["competitors", "listed_companies"],
    },
}

ANALYSIS_TOOL = {
    "name": "submit_briefing",
    "description": "Submit the complete briefing analysis as one JSON object.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_summary": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": _STATEMENT_SCHEMA,
                "description": "1-3 short statements covering what the company does, who the "
                "founders are and their prior experience, and funding/investors — the whole "
                "'about this company' picture in a few sentences, not a bulleted list.",
            },
            "market": _MARKET_SCHEMA,
            "competitors": {"type": "array", "items": _STATEMENT_SCHEMA},
            "risks": {"type": "array", "items": _RISK_ITEM_SCHEMA},
            "commercial": {
                "type": "object",
                "properties": {
                    "pricing_comparison": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": _PRICING_ROW_SCHEMA,
                    },
                    "listed_comparables": {
                        "type": "array",
                        "minItems": 0,
                        "maxItems": 2,
                        "items": _LISTED_COMPARABLE_SCHEMA,
                    },
                    "mismatches": {"type": "array", "items": _MISMATCH_SCHEMA},
                },
                "required": ["pricing_comparison", "listed_comparables", "mismatches"],
            },
            "gaps": {
                "type": "array",
                "minItems": 14,
                "maxItems": 14,
                "items": _GAP_RESULT_SCHEMA,
            },
            "risk_questions": {
                "type": "array",
                "minItems": 8,
                "maxItems": 10,
                "items": _RISK_QUESTION_SCHEMA,
                "description": (
                    "Exactly 8 to 10 ranked questions about legal, regulatory, reputational, or "
                    "execution risk, each with a one-clause 'why'. The final briefing needs 10-15 "
                    "questions total (mismatch questions, then gap questions, then these), and "
                    "mismatch/gap questions may be few or zero — so always provide the full 8 to "
                    "10 here regardless of how much risk evidence exists."
                ),
            },
            "scorecard": {
                "type": "array",
                "minItems": 5,
                "maxItems": 5,
                "items": _SCORECARD_DIM_SCHEMA,
            },
        },
        "required": [
            "company_summary",
            "market",
            "competitors",
            "risks",
            "commercial",
            "gaps",
            "risk_questions",
            "scorecard",
        ],
    },
}


def entity_prompt(company: str, website: str, category: str, evidence_items: list[dict]) -> str:
    evidence_block = _format_evidence(evidence_items)
    return (
        f"{GOVERNING_RULE}\n\n"
        f"Company: {company}\nWebsite: {website}\nCategory: {category}\n\n"
        "From the evidence below, identify:\n"
        "1. Exactly three direct competitors of this company, each with a name and primary domain. "
        "If this category has well-known, widely recognized players, name the most prominent ones "
        "even if the evidence only hints at the category rather than naming them directly — draw "
        "on your own knowledge of the space rather than settling for obscure or tangential names.\n"
        "2. Any publicly listed companies that are genuinely comparable (0, 1, or 2). Only name a "
        "company that is actually publicly traded today. If no real public comparable exists for "
        "this category, return an empty list rather than forcing an unrelated or private company "
        "into this slot.\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Call submit_entities with your answer."
    )


def analysis_prompt(company: str, website: str, category: str, evidence_items: list[dict]) -> str:
    evidence_block = _format_evidence(evidence_items)
    gap_block = "\n".join(f"{g['no']}. {g['item']} (priority {g['priority']})" for g in GAP_ITEMS)
    return (
        f"{GOVERNING_RULE}\n\n"
        f"Company: {company}\nWebsite: {website}\nCategory: {category}\n\n"
        "Using only the evidence below, build the full briefing. Keep every piece of free text "
        "(statement `text`, rationale, claim, why_it_matters, question, why) to one short sentence, "
        "under 20 words — be terse, this is a scan-able briefing, not a report. Never restate the "
        "same fact in two different sections.\n\n"
        "Confidence labels: use \"Corroborated\" only when at least two distinct source domains, with "
        "titles that are not near-duplicates, support the statement. Use \"Single source\" when only one "
        "domain supports it. Use \"Inferred\" for conclusions drawn from signals such as hiring, always "
        "citing the signal evidence.\n\n"
        "company_summary: 1-3 statements covering what the company does, the founders and their prior "
        "experience, and funding rounds/investors. This replaces a long bio — be selective, not "
        "exhaustive.\n\n"
        "market: give a verdict — is this market Expanding, Saturated, Mixed, or Nascent — with a "
        "one-sentence justification, then 2-4 supporting points grounded in the interest-over-time "
        "trend, the company's interest vs. the category's, how many competitors are crowding in, and "
        "relevant category news. The reader should walk away knowing whether this company is entering "
        "a wide-open space or a crowded one.\n\n"
        "competitors: one line per competitor (what they do, how they differ), plus one line per "
        "listed comparable if any exist.\n\n"
        "risks: one line per distinct risk, each tagged with a category (legal, regulatory, "
        "founder_history, reputational, competitive, other). Actively look for lawsuits, regulatory "
        "actions, controversies, complaints, and any sign of a founder's earlier failed startup — "
        "one line per issue, not one line per article.\n\n"
        "Commercial Reality Check: extract pricing only from search titles and snippets. Build four "
        "`pricing_comparison` rows — the company, then its three named competitors, in that order — "
        "using their own pricing pages. `listed_comparables` is a completely different, separate list: "
        "it holds ONLY stock-market data for genuinely publicly-traded companies, built exclusively "
        "from evidence tagged with engine `google_finance` (price, market cap, price movement). Never "
        "put a competitor's pricing-page data into `listed_comparables`, and never put stock data into "
        "`pricing_comparison` — a company can appear in both lists only if it is both a named "
        "competitor AND has its own google_finance evidence. This is a mechanical rule: scan the "
        "evidence for every item tagged engine google_finance and create exactly one listed_comparables "
        "row per one — do this even if you already mentioned that company elsewhere (e.g. in "
        "competitors); mentioning it elsewhere is never a substitute for the row here. If there is no "
        "google_finance evidence at all, `listed_comparables` must be an empty list — do not invent or "
        "substitute a row. Then test "
        "exactly these four mismatch rules and include a row only for each one that fires:\n"
        "- positioning_gap: company evidence claims enterprise positioning and the lowest public plan is "
        "self-serve\n"
        "- free_tier_gap: the company and its competitors differ on offering a free tier\n"
        "- hidden_pricing: no public pricing is found for the company\n"
        "- bundling_threat: evidence shows a competitor or listed company bundling the same capability "
        "into an existing product\n\n"
        f"Gap checklist: assess each of these 14 fixed items against the evidence. Read every piece of "
        f"evidence carefully before marking something Missing — founder background, free-tier terms, and "
        f"usage limits are often stated plainly in a snippet and should be marked Found when they are. "
        f"For each item return its `no`, a status of Found/Partial/Missing, the evidence IDs behind that "
        f"status, and (only if Partial or Missing) one question to ask the founders plus one short clause "
        f"on why it matters:\n{gap_block}\n\n"
        "Risk questions: propose exactly 8 to 10 ranked questions about legal, regulatory, reputational, "
        "or execution risk, each with a one-clause 'why', grounded in the risks section where evidence "
        "supports it and falling back to sound general questions for this category where it doesn't. The "
        "final briefing needs 10 to 15 questions in total (mismatch questions, then gap questions, then "
        "these), and there may be few or no mismatch or gap questions — always supply the full 8 to 10 "
        "here so the total still reaches at least 10.\n\n"
        "Scorecard: score Team, Traction, Market, Defensibility, and Risk from 1 to 5 (on Risk, a higher "
        "score means lower risk). Always give a number — if evidence is thin, give your best grounded "
        "estimate and say so plainly in the rationale (e.g. 'limited evidence, estimated from category "
        "norms') rather than leaving it blank.\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Call submit_briefing with your answer."
    )


_MAX_SNIPPET_CHARS = 220


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _format_evidence(evidence_items: list[dict]) -> str:
    lines = []
    for item in evidence_items:
        stale = " [STALE]" if item.get("stale") else ""
        date = item.get("published_date") or "undated"
        title = _truncate(item["title"], 100)
        snippet = _truncate(item["snippet"], _MAX_SNIPPET_CHARS)
        lines.append(f"[{item['id']}] ({item['engine']}, {item['source_domain']}, {date}{stale}) {title} — {snippet}")
    return "\n".join(lines) if lines else "(no evidence)"
