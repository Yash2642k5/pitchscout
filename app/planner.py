"""Builds the 16 SerpApi searches for a briefing request.

This is the only module that constructs search queries. Searches 12-16
depend on entities discovered from wave 1 (three competitors, two tickers),
so they are planned separately once those entities are known.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannedSearch:
    no: int
    wave: int
    engine: str
    params: dict


def plan_wave_1(company: str, website: str, category: str) -> list[PlannedSearch]:
    """Searches 1-11. Depend only on the three request inputs."""
    common = {"hl": "en", "gl": "in"}
    return [
        PlannedSearch(1, 1, "google", {**common, "q": f'"{company}" {category}'}),
        PlannedSearch(2, 1, "google", {**common, "q": f'"{company}" founder OR co-founder OR CEO'}),
        PlannedSearch(3, 1, "google", {**common, "q": f"{company} competitors alternatives"}),
        PlannedSearch(4, 1, "google", {**common, "q": f"{company} pricing plans"}),
        PlannedSearch(5, 1, "google_news", {**common, "q": f'"{company}"'}),
        PlannedSearch(6, 1, "google_news", {**common, "q": f'"{company}" funding OR raises OR investors'}),
        PlannedSearch(7, 1, "google_news", {**common, "q": category}),
        PlannedSearch(8, 1, "google_jobs", {**common, "q": company}),
        PlannedSearch(9, 1, "google_trends", {"q": f"{company},{category}"}),
        PlannedSearch(10, 1, "google_play", {**common, "q": company}),
        PlannedSearch(11, 1, "google_shopping", {**common, "q": company}),
    ]


def plan_wave_2(competitors: list[dict], tickers: list[str]) -> list[PlannedSearch]:
    """Searches 12-16. Depend on the entity call's output.

    competitors: list of up to 3 dicts with a "name" key (order preserved).
    tickers: list of up to 2 ticker strings, e.g. "AAPL:NASDAQ".
    """
    common = {"hl": "en", "gl": "in"}
    searches: list[PlannedSearch] = []
    for i in range(3):
        name = competitors[i]["name"] if i < len(competitors) else None
        no = 12 + i
        params = {**common, "q": f"{name} pricing plans"} if name else {**common, "q": ""}
        searches.append(PlannedSearch(no, 2, "google", params))
    for i in range(2):
        ticker = tickers[i] if i < len(tickers) else None
        no = 15 + i
        params = {"q": ticker} if ticker else {"q": ""}
        searches.append(PlannedSearch(no, 2, "google_finance", params))
    return searches


def plan_all(
    company: str,
    website: str,
    category: str,
    competitors: list[dict] | None = None,
    tickers: list[str] | None = None,
) -> list[PlannedSearch]:
    """Convenience: full 16-search plan once wave 1 entities are known."""
    searches = plan_wave_1(company, website, category)
    searches += plan_wave_2(competitors or [], tickers or [])
    return searches
