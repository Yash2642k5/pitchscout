"""Prompts and output JSON schemas for both LLM calls.

Call 1 (entity call) proposes competitors and listed comparables from wave 1
evidence. Call 2 (analysis call) reasons over all evidence and returns the
overview, key facts, market read, competitors, risks, the Commercial Reality
Check, the news read, the trajectory, the diligence list, and the scorecard,
as one JSON object shaped by ANALYSIS_TOOL's input_schema. Both calls are
forced into that shape through tool use.

The diligence list is the one place questions live. Each row carries both
what the evidence established and the question that follows from it, so the
briefing never shows a "what's missing" item next to a separate question
list that repeats it.
"""

from typing import Any

GOVERNING_RULE = (
    "You are an analyst assistant. You may use ONLY the evidence items given to you. "
    "Every statement you write must cite the evidence IDs (e.g. \"e03\") that support it. "
    "Never invent a fact, a number, a name, or a URL that is not present in the evidence. "
    "If the evidence does not support a claim, do not make the claim."
)

# The diligence areas every briefing must assess. Unlike a fixed checklist of
# item names, these are the ground an analyst has to cover; the model names the
# specific topic it found under each area, so a row reads as a finding about
# this company rather than a box that went unticked. Areas whose answer lives
# in a search result rather than in a founder's head (a competitor's public
# price, a stock quote, an app-store listing) are deliberately absent — those
# belong to the Commercial Reality Check and the search-coverage strip.
DILIGENCE_AREAS = [
    "Team and founders",
    "Funding and investors",
    "Customers and traction",
    "Pricing and monetization",
    "Product and differentiation",
    "Market and competition",
    "Hiring and execution capacity",
    "Risk and governance",
]

DILIGENCE_STATUSES = ["Found", "Partial", "Missing"]

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

_OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {
            "type": "string",
            "description": (
                "What this company is, in one sentence under 20 words, written the way an "
                "analyst would open a memo. Name the product and who buys it."
            ),
        },
        "paragraph": {
            "type": "string",
            "description": (
                "One flowing paragraph of 4 to 6 sentences, 70 to 130 words, covering what the "
                "company sells, who it sells to, who founded it and what they did before, and "
                "how it is funded. Continuous prose, not a list, no bullet markers, no headings."
            ),
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["one_liner", "paragraph", "evidence"],
}

_KEY_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "2-4 words, e.g. 'Latest round', 'Founders'."},
        "value": {"type": "string", "description": "The fact itself, under 14 words."},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["label", "value", "evidence"],
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

_NEWS_HIGHLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exactly one evidence ID: the news item being read.",
        },
        "so_what": {
            "type": "string",
            "description": (
                "One sentence under 22 words on what this means for the company's position — "
                "never a restatement of the headline, which the reader can already see."
            ),
        },
    },
    "required": ["evidence", "so_what"],
}

_TRAJECTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": (
                "Where this company is heading, in under 12 words, e.g. "
                "'Repositioning from data catalog to AI context layer'."
            ),
        },
        "paragraph": {
            "type": "string",
            "description": (
                "One flowing paragraph of 3 to 5 sentences, 60 to 110 words, on where the "
                "company is heading: what the recent news, hiring, funding and market trend "
                "together point to, and what has to go right for it to work. Reason forward "
                "from the evidence; label the reasoning as inference in the signals rather "
                "than presenting it as fact. Continuous prose, no bullet markers."
            ),
        },
        "signals": {
            "type": "array",
            "items": _STATEMENT_SCHEMA,
            "description": (
                "2-4 directional signals behind the read — a hire, a round, a launch, a trend "
                "line, a competitor move. Use confidence 'Inferred' for anything you concluded "
                "rather than read directly."
            ),
        },
    },
    "required": ["headline", "paragraph", "signals"],
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

_DILIGENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "area": {
            "type": "string",
            "enum": DILIGENCE_AREAS,
            "description": "Which diligence area this row sits under.",
        },
        "topic": {
            "type": "string",
            "description": (
                "What this row is about, in 2-5 words, specific to this company — "
                "'Series C use of proceeds', not 'Funding'."
            ),
        },
        "status": {
            "type": "string",
            "enum": DILIGENCE_STATUSES,
            "description": "How well the evidence covers this topic.",
        },
        "found": {
            "type": "string",
            "description": (
                "One sentence, under 25 words, on what the evidence actually establishes here. "
                "Required on every row, including Missing ones — on those, say what little is "
                "known, or 'Nothing in the evidence' when truly nothing."
            ),
        },
        "question": {
            "type": "string",
            "description": (
                "The question to put to the founders, following the question rules in the "
                "prompt. Required on every row, including Found ones."
            ),
        },
        "why": {
            "type": "string",
            "description": "One clause, under 15 words, on why an investor needs the answer.",
        },
        "priority": {
            "type": "integer",
            "description": "1 to ask first, 2 to ask if time allows, 3 for follow-up email.",
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["area", "topic", "status", "found", "question", "why", "priority", "evidence"],
}

_PRICING_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "lowest_paid_plan": {"type": "string", "description": "'Not found' if absent"},
        "free_tier": {"type": "string", "description": "'Yes', 'No', or 'Not found'"},
        "contact_sales_tier": {"type": "string", "description": "'Yes', 'No', or 'Not found'"},
        "pricing_source": {
            "type": "string",
            "description": (
                "Where the figure came from: 'Vendor page', 'Third party', or 'Not found'."
            ),
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "name",
        "lowest_paid_plan",
        "free_tier",
        "contact_sales_tier",
        "pricing_source",
        "evidence",
    ],
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
            "overview": _OVERVIEW_SCHEMA,
            "key_facts": {
                "type": "array",
                "minItems": 3,
                "maxItems": 8,
                "items": _KEY_FACT_SCHEMA,
                "description": (
                    "3-8 scannable facts an analyst wants at a glance: founders, latest round, "
                    "investors, named customers, headcount signals, founded year, HQ. Only "
                    "facts the evidence states."
                ),
            },
            "market": _MARKET_SCHEMA,
            "competitors": {"type": "array", "items": _STATEMENT_SCHEMA},
            "news_highlights": {
                "type": "array",
                "minItems": 0,
                "maxItems": 6,
                "items": _NEWS_HIGHLIGHT_SCHEMA,
                "description": (
                    "The 3-6 most consequential recent news items, newest first, each read for "
                    "what it means. Prefer items dated in the last 12 months and skip anything "
                    "marked [STALE]. Return an empty list only if there is no news evidence."
                ),
            },
            "trajectory": _TRAJECTORY_SCHEMA,
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
            "diligence": {
                "type": "array",
                "minItems": 8,
                "maxItems": 14,
                "items": _DILIGENCE_SCHEMA,
                "description": (
                    "8-14 rows. Cover each of the eight diligence areas at least once, then add "
                    "rows for anything company-specific the evidence raises. Every row carries "
                    "both what you found and the question that follows from it."
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
            "overview",
            "key_facts",
            "market",
            "competitors",
            "news_highlights",
            "trajectory",
            "risks",
            "commercial",
            "diligence",
            "scorecard",
        ],
    },
}


def entity_prompt(company: str, website: str, category: str, evidence_items: list[dict]) -> str:
    evidence_block = _format_evidence(
        evidence_items,
        shapes={no: _ENTITY_SHAPE for no in _ENTITY_SEARCH_NOS},
        default=_ENTITY_SHAPE,
        only=_ENTITY_SEARCH_NOS,
    )
    return (
        f"{GOVERNING_RULE}\n\n"
        f"Company: {company}\nWebsite: {website}\nCategory: {category}\n\n"
        "From the evidence below, identify:\n"
        "1. Exactly three direct competitors of this company, each with a name and primary "
        "domain. Pick companies a buyer would actually evaluate against this one — same "
        "category, same buyer, comparable product. If this category has well-known players, "
        "name the most prominent ones even if the evidence only hints at the category rather "
        "than naming them directly; draw on your own knowledge of the space rather than "
        "settling for obscure or tangential names.\n"
        "2. Publicly listed companies that are genuinely comparable (0, 1, or 2). This slot is "
        "strict, and an empty list is the correct answer more often than not:\n"
        "   - The company must be listed and trading TODAY. Do not name a company that has been "
        "acquired, taken private, or delisted.\n"
        "   - Its primary business must be this category. A pure-play competitor qualifies; a "
        "diversified mega-cap that happens to ship a product in this space does not, because "
        "its share price says nothing about this category.\n"
        "   - If no listed pure-play exists, return an empty list. An empty list is a useful "
        "finding. A loosely related ticker is worse than nothing, because it puts a misleading "
        "comparable in front of an analyst.\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Call submit_entities with your answer."
    )


_QUESTION_RULES = """\
Questions are the most valuable thing in this briefing. An analyst reads them straight off \
the screen and asks them in a live meeting, so each one has to earn its airtime. Every row \
in `diligence` carries one.

Write each question so that:
  - It names something specific to THIS company — a number, a product, a customer, a \
competitor, a date, a role you saw posted, or a claim from the evidence.
  - Only the founders could answer it. Never ask for something the evidence already \
answered, and never ask the founders about a third party's public pricing, share price, or \
app-store presence.
  - It attacks the commercial, technical, or competitive weak point the evidence exposes — \
not the absence of a search result.
  - It is open-ended enough to produce a real answer, not a yes or no.
  - It is one sentence, under 25 words.

Build the question out of what you found. When the evidence establishes a fact, put the fact \
in the question and push past it, rather than asking whether the fact exists.

Good: "Your pricing page names tiers but no rates — what does a median enterprise deployment \
cost in year one?"
Good: "Alation publishes $60K/year list pricing; how do you close deals when buyers cannot \
benchmark you against it?"
Good: "Two of your eight open roles are ML — how does a team that size ship the context layer \
against Collibra's R&D base?"
Good: "You name three logos publicly; what share of ARR do your top five customers account \
for today?"

Bad: "What are the pricing tiers and rates for the company?" — a search already answered this.
Bad: "What are the pricing tiers of Alation, Collibra, and Informatica?" — asks the founders \
about competitors' public pricing.
Bad: "Is the company available in any app stores or shopping platforms?" — irrelevant to \
enterprise software, and it is a search result, not a diligence gap.
Bad: "Do you have open ML or research engineering roles?" — the evidence already answers this.
Bad: "Who are your founders and what did they do before?" — the evidence already answers this.
Bad: "Do you track market cap or stock data for listed competitors?" — not a question about \
this business at all."""


def analysis_prompt(
    company: str,
    website: str,
    category: str,
    evidence_items: list[dict],
    role_mix_note: str | None = None,
) -> str:
    """Builds the analysis prompt.

    `role_mix_note` carries the role mix the pipeline already computed in code from the
    jobs evidence. It is passed in as settled fact so the model reasons from it instead of
    re-deriving it from truncated job snippets and contradicting the number the briefing
    itself displays.
    """
    evidence_block = _format_evidence(evidence_items)
    area_block = "\n".join(f"- {area}" for area in DILIGENCE_AREAS)
    computed_block = (
        f"\nAlready established in code from the jobs evidence, treat as fact:\n{role_mix_note}\n"
        if role_mix_note
        else ""
    )
    return (
        f"{GOVERNING_RULE}\n\n"
        f"Company: {company}\nWebsite: {website}\nCategory: {category}\n"
        f"{computed_block}\n"
        "You are writing for an investment analyst reading this on one screen before a founder "
        "meeting. They want density and specifics. Keep every short field to one sentence under "
        "20 words; `overview.paragraph` and `trajectory.paragraph` are the exceptions and should "
        "run their full stated length. Never restate a fact in two sections.\n\n"
        "Confidence: \"Corroborated\" only when two distinct source domains with non-duplicate "
        "titles support the statement; \"Single source\" when one domain does; \"Inferred\" for "
        "conclusions drawn from signals such as hiring, always citing the signal.\n\n"
        "overview: `one_liner` is what this company is, in one sentence. `paragraph` is 4-6 "
        "sentences of continuous prose on the product, the buyer, the founders and their prior "
        "experience, and the funding — prose an analyst would read aloud, not a list of facts.\n\n"
        "key_facts: 3-8 facts worth a glance — founders, latest round, investors, named "
        "customers, founded year, HQ. Only what the evidence states.\n\n"
        "market: a verdict (Expanding, Saturated, Mixed, Nascent) with a one-sentence "
        "justification, then 2-4 points grounded in the interest trend, the company's interest "
        "vs. the category's, competitive density, and category news.\n\n"
        "competitors: one line per competitor — what they do, how they differ.\n\n"
        "news_highlights: the 3-6 most consequential recent google_news items, newest first. The "
        "reader already sees the headline and date, so `so_what` must say what the item means for "
        "this company's position — a read, not a summary. Skip [STALE] items and anything really "
        "about another company.\n\n"
        "trajectory: close by reasoning forward. Read the news, hiring mix, funding and market "
        "trend together, say where the company is heading and what has to go right. This is the "
        "one section that reasons beyond the evidence — do it openly and mark concluded signals "
        "\"Inferred\".\n\n"
        "risks: one line per distinct risk, tagged legal, regulatory, founder_history, "
        "reputational, competitive or other. Hunt for lawsuits, regulatory actions, "
        "controversies, complaints and any earlier failed startup — one line per issue, not per "
        "article.\n\n"
        "Commercial Reality Check: extract pricing from titles and snippets into four "
        "`pricing_comparison` rows — the company, then its three competitors, in that order.\n"
        "- Vendor pricing pages come first but are not the only source. Review sites, comparison "
        "pages, procurement and marketplace listings and analyst write-ups often publish the "
        "number the vendor hides, and a cited third-party figure beats 'Not found' every time. "
        "Use it and set `pricing_source` to 'Third party'; use 'Vendor page' for the vendor's "
        "own.\n"
        "- A list price, contract value, per-seat rate, per-unit rate, or a floor such as "
        "'starts at $100K+/year' all count. Write the figure as the source states it.\n"
        "- Write 'Not found' only when no evidence carries any figure for that company. If "
        "pricing exists but is quote-only, that is itself the finding — write 'Tiers named, no "
        "public rate' rather than 'Not found'.\n"
        "- `listed_comparables` is a separate list holding ONLY stock data, built exclusively "
        "from evidence tagged engine `google_finance`: one row per such item, even if you named "
        "that company under competitors. Never put pricing data here or stock data in "
        "`pricing_comparison`. No google_finance evidence means an empty list, not an invented "
        "row.\n"
        "Then include a row for each of these four rules that actually fires:\n"
        "- positioning_gap: evidence claims enterprise positioning but the lowest public plan is "
        "self-serve\n"
        "- free_tier_gap: the company and its competitors differ on offering a free tier\n"
        "- hidden_pricing: no public pricing is found for the company\n"
        "- bundling_threat: a competitor or listed company bundles the same capability into an "
        "existing product\n\n"
        "diligence: the briefing's working section, replacing both a gap checklist and a "
        f"separate question list. Return 8-14 rows covering each area at least once:\n{area_block}\n"
        "Then add rows for what this company specifically raises — a repositioning, a "
        "concentration risk, a technical claim, a competitive squeeze.\n"
        "- Status: Found when the evidence answers the area well, Partial when it answers part, "
        "Missing when it says nothing useful. Read the snippets properly first — founder "
        "backgrounds, funding amounts, customer names and free-tier terms are often stated "
        "plainly, and marking a found fact Missing is the worst error you can make here. "
        "Anything in the `Already established in code` note above is Found.\n"
        "- `found` is one sentence on what the evidence establishes; a Found row still carries a "
        "question, one level deeper than what the evidence already says.\n"
        "- Priority 1 is what the analyst must ask in the meeting. Rank on how much the answer "
        "would move an investment decision, not on how thin the evidence was.\n\n"
        f"{_QUESTION_RULES}\n\n"
        "Scorecard: score Team, Traction, Market, Defensibility and Risk 1-5 (on Risk, higher "
        "means lower risk). Always give a number — on thin evidence give your best grounded "
        "estimate and say so in the rationale rather than leaving it blank.\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Call submit_briefing with your answer."
    )


_MAX_TITLE_CHARS = 105

# Per-search shaping for the prompts. SerpApi returns up to eight results per search,
# but they are not equally worth their tokens: a job description says nothing the title
# and the code-computed role mix have not already said, a news headline carries its own
# signal without the snippet, and a pricing snippet is where the only real figure in the
# briefing tends to hide — mid-sentence, after the vendor's preamble. Each search
# therefore declares how many items it contributes and how much of each snippet
# survives, which keeps the prompt inside a tight per-minute token budget without
# starving the sections that depend on detail.
#
# Trimming here only limits what the model may cite. The full evidence map still ships
# with the briefing, so the search-coverage strip and every chip stay complete.
_SHAPES: dict[int, tuple[int, int]] = {
    1: (4, 165),    # what the company does — the vendor pages in search 4 add to this
    2: (5, 165),    # founders and their background
    3: (5, 185),    # competitors and alternatives
    4: (6, 300),    # the company's own pricing
    5: (5, 100),    # news — the headline is the signal
    6: (6, 100),    # funding news
    7: (4, 100),    # category news
    8: (4, 60),     # jobs — the role mix is already computed in code from every title
    9: (1, 230),    # trends summary, already condensed by the normalizer
    10: (1, 60),    # app listing
    11: (2, 60),    # shopping listing
    12: (5, 300),   # competitor pricing
    13: (5, 300),
    14: (5, 300),
    15: (1, 230),   # finance summary
    16: (1, 230),
}
_SHAPE_DEFAULT = (6, 150)

# The entity call only has to name three competitors and any listed comparable, so it
# reads the three searches that speak to positioning instead of the whole wave. Keeping
# it small matters twice over: it shares a per-minute token budget with the analysis
# call that follows it seconds later.
_ENTITY_SEARCH_NOS = (1, 3, 7)
_ENTITY_SHAPE = (6, 130)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _evidence_line(item: dict, snippet_chars: int) -> str:
    stale = " [STALE]" if item.get("stale") else ""
    date = item.get("published_date") or "undated"
    title = _truncate(item["title"], _MAX_TITLE_CHARS)
    snippet = _truncate(item["snippet"], snippet_chars)
    return (
        f"[{item['id']}] ({item['engine']}, {item['source_domain']}, {date}{stale}) "
        f"{title} — {snippet}"
    )


def _format_evidence(
    evidence_items: list[dict],
    shapes: dict[int, tuple[int, int]] | None = None,
    default: tuple[int, int] = _SHAPE_DEFAULT,
    only: tuple[int, ...] | None = None,
) -> str:
    """Renders evidence for a prompt, shaped per search and in evidence-ID order."""
    shapes = _SHAPES if shapes is None else shapes
    kept_per_search: dict[int, int] = {}
    lines = []
    for item in evidence_items:
        search_no = item.get("search_no")
        if only is not None and search_no not in only:
            continue
        max_items, snippet_chars = shapes.get(search_no, default)
        used = kept_per_search.get(search_no, 0)
        if used >= max_items:
            continue
        kept_per_search[search_no] = used + 1
        lines.append(_evidence_line(item, snippet_chars))
    return "\n".join(lines) if lines else "(no evidence)"
