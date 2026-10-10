"""Builds the 18 SerpApi searches for a briefing request.

This is the only module that constructs search queries. Searches 12-18
depend on entities discovered from wave 1 (three competitors and the subject's
ticker), so they are planned separately once those entities are known.

Searches 16-18 exist because SerpApi has no engine that returns a market share
or a brand valuation. Those numbers only exist in what somebody published, so
they are fetched as ordinary web and news results and read off the evidence by
the analysis call, which may only report a figure a source actually states.
"""

from dataclasses import dataclass

# Google Finance defaults to a one-day graph. A briefing is a read on where a
# company is heading, so the stock panel asks for a year instead.
STOCK_WINDOW = "1Y"


@dataclass(frozen=True)
class PlannedSearch:
    no: int
    wave: int
    engine: str
    params: dict


def plan_wave_1(company: str, website: str, category: str, gl: str = "us") -> list[PlannedSearch]:
    """Searches 1-11. Depend only on the three request inputs."""
    common = {"hl": "en", "gl": gl}
    return [
        PlannedSearch(1, 1, "google", {**common, "q": f'{company} {category}'}),
        PlannedSearch(2, 1, "google", {**common, "q": f'{company} founder OR co-founder OR CEO'}),
        PlannedSearch(3, 1, "google", {**common, "q": f"{company} competitors alternatives"}),
        PlannedSearch(4, 1, "google", {**common, "q": f"{company} pricing plans"}),
        PlannedSearch(5, 1, "google_news", {**common, "q": f'{company}'}),
        PlannedSearch(6, 1, "google_news", {**common, "q": f'{company} funding OR raises OR investors'}),
        PlannedSearch(7, 1, "google_news", {**common, "q": category}),
        PlannedSearch(8, 1, "google_jobs", {**common, "q": company}),
        PlannedSearch(9, 1, "google_trends", {"q": f"{company},{category}"}),
        PlannedSearch(10, 1, "google_play", {**common, "q": company}),
        PlannedSearch(11, 1, "google_shopping", {**common, "q": company}),
    ]


def plan_wave_2(
    company: str,
    category: str,
    competitors: list[dict],
    subject_ticker: str = "",
    gl: str = "us",
) -> list[PlannedSearch]:
    """Searches 12-18. Depend on the entity call's output.

    competitors: list of up to 3 dicts with a "name" key (order preserved).
    subject_ticker: the ticker whose price graph heads the briefing, formatted
        TICKER:EXCHANGE. Empty when nothing listed was found, which leaves
        search 15 blank and the stock panel in its empty state.
    """
    common = {"hl": "en", "gl": gl}
    searches: list[PlannedSearch] = []

    for i in range(3):
        name = competitors[i]["name"] if i < len(competitors) else None
        params = {**common, "q": f"{name} pricing plans"} if name else {**common, "q": ""}
        searches.append(PlannedSearch(12 + i, 2, "google", params))

    searches.append(
        PlannedSearch(
            15, 2, "google_finance",
            {"q": subject_ticker, "window": STOCK_WINDOW} if subject_ticker else {"q": ""},
        )
    )
    searches.append(
        PlannedSearch(16, 2, "google", {**common, "q": f'{company} market share percent {category}'})
    )
    searches.append(
        PlannedSearch(17, 2, "google", {**common, "q": f'{company} brand value OR valuation OR "valued at"'})
    )
    searches.append(
        PlannedSearch(18, 2, "google_news", {**common, "q": f'{company} market share OR brand value OR valuation'})
    )
    return searches


def plan_all(
    company: str,
    website: str,
    category: str,
    competitors: list[dict] | None = None,
    subject_ticker: str = "",
) -> list[PlannedSearch]:
    """Convenience: full 18-search plan once wave 1 entities are known."""
    searches = plan_wave_1(company, website, category)
    searches += plan_wave_2(company, category, competitors or [], subject_ticker)
    return searches
