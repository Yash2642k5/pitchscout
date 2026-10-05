"""One function per SerpApi engine: raw response to evidence items.

Each normalizer keeps the top eight results from the raw response, applies
the name filter (searches 1, 2, 5, 6 only), and returns a list of
schema-valid evidence items built through evidence.build_evidence_item.
An empty or malformed response converts to an empty list; normalizers
never raise.
"""

from datetime import datetime
from typing import Any

from .evidence import IdCounter, build_evidence_item, passes_name_filter

MAX_RESULTS = 8


def _emit(
    candidates: list[dict[str, Any]],
    search_no: int,
    engine: str,
    retrieved_at: datetime,
    id_counter: IdCounter,
    company: str,
    website: str,
) -> list[dict[str, Any]]:
    items = []
    for c in candidates[:MAX_RESULTS]:
        if not passes_name_filter(search_no, company, website, c["title"], c["snippet"], c["url"]):
            continue
        items.append(
            build_evidence_item(
                id_counter,
                search_no,
                engine,
                c["title"],
                c["snippet"],
                c["url"],
                c.get("published_date_raw"),
                retrieved_at,
            )
        )
    return items


def normalize_google(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    results = raw.get("organic_results") or []
    candidates = [
        {
            "title": r.get("title") or "",
            "snippet": r.get("snippet") or "",
            "url": r.get("link") or "",
            "published_date_raw": r.get("date"),
        }
        for r in results
    ]
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_news(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    results = raw.get("news_results") or []
    candidates = []
    for r in results:
        source = r.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        snippet = r.get("snippet") or (f"{source_name}" if source_name else "")
        candidates.append(
            {
                "title": r.get("title") or "",
                "snippet": snippet,
                "url": r.get("link") or "",
                "published_date_raw": r.get("date"),
            }
        )
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_jobs(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    results = raw.get("jobs_results") or []
    candidates = []
    for r in results:
        apply_options = r.get("apply_options") or []
        url = apply_options[0].get("link") if apply_options else (r.get("share_link") or "")
        extensions = r.get("detected_extensions") or {}
        candidates.append(
            {
                "title": r.get("title") or "",
                "snippet": (r.get("description") or "")[:400],
                "url": url or "",
                "published_date_raw": extensions.get("posted_at"),
            }
        )
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_trends(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    """Trends has no result list; it is turned into one summary evidence item."""
    timeline = (raw.get("interest_over_time") or {}).get("timeline_data") or []
    if not timeline:
        return []

    def series_values(point: dict, index: int) -> int:
        values = point.get("values") or []
        if index < len(values):
            try:
                return int(values[index].get("extracted_value", values[index].get("value", 0)))
            except (TypeError, ValueError):
                return 0
        return 0

    company_series = [series_values(p, 0) for p in timeline]
    category_series = [series_values(p, 1) for p in timeline]

    def direction(series: list[int]) -> str:
        if len(series) < 2:
            return "flat"
        first, last = series[0], series[-1]
        if last > first:
            return "rising"
        if last < first:
            return "declining"
        return "flat"

    company_dir = direction(company_series)
    category_dir = direction(category_series)
    company_avg = sum(company_series) / len(company_series) if company_series else 0
    category_avg = sum(category_series) / len(category_series) if category_series else 0

    title = f"Google Trends: {company} vs {category}"
    snippet = (
        f"{company} search interest is {company_dir} (avg {company_avg:.0f}/100). "
        f"{category} category interest is {category_dir} (avg {category_avg:.0f}/100)."
    )
    candidates = [
        {
            "title": title,
            "snippet": snippet,
            "url": f"https://trends.google.com/trends/explore?q={company},{category}",
            "published_date_raw": None,
        }
    ]
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_play(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    results = raw.get("organic_results") or []
    candidates = []
    for r in results:
        rating = r.get("rating")
        reviews = r.get("reviews") or r.get("ratings")
        price = r.get("price") if r.get("price") not in (None, "") else "Free"
        parts = []
        if rating is not None:
            parts.append(f"Rating: {rating}")
        if reviews is not None:
            parts.append(f"{reviews} reviews")
        parts.append(f"Price: {price}")
        candidates.append(
            {
                "title": r.get("title") or "",
                "snippet": ". ".join(parts),
                "url": r.get("link") or "",
                "published_date_raw": None,
            }
        )
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_shopping(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    results = raw.get("shopping_results") or []
    candidates = []
    for r in results:
        price = r.get("price") or r.get("extracted_price")
        source = r.get("source") or ""
        rating = r.get("rating")
        parts = [f"Price: {price}" if price else "Price: not listed"]
        if source:
            parts.append(f"Seller: {source}")
        if rating is not None:
            parts.append(f"Rating: {rating}")
        candidates.append(
            {
                "title": r.get("title") or "",
                "snippet": ". ".join(parts),
                "url": r.get("link") or r.get("product_link") or "",
                "published_date_raw": None,
            }
        )
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


def normalize_google_finance(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    summary = raw.get("summary") or {}
    if not summary:
        return []
    title = summary.get("title") or summary.get("stock") or ""
    price = summary.get("price")
    currency = summary.get("currency") or ""
    change = summary.get("price_change") or summary.get("change")
    change_pct = summary.get("price_change_percent") or summary.get("change_percent")
    market = summary.get("market") or {}
    market_cap = market.get("market_cap") or summary.get("market_cap")
    parts = []
    if price is not None:
        parts.append(f"Price: {price} {currency}".strip())
    if change is not None or change_pct is not None:
        parts.append(f"Change: {change} ({change_pct})")
    if market_cap is not None:
        parts.append(f"Market cap: {market_cap}")
    stock = summary.get("stock") or ""
    candidates = [
        {
            "title": f"{title} ({stock})" if stock else title,
            "snippet": ". ".join(parts) if parts else "No financial summary available.",
            "url": f"https://www.google.com/finance/quote/{stock}" if stock else "https://www.google.com/finance",
            "published_date_raw": None,
        }
    ]
    return _emit(candidates, search_no, engine, retrieved_at, id_counter, company, website)


NORMALIZERS = {
    "google": normalize_google,
    "google_news": normalize_google_news,
    "google_jobs": normalize_google_jobs,
    "google_trends": normalize_google_trends,
    "google_play": normalize_google_play,
    "google_shopping": normalize_google_shopping,
    "google_finance": normalize_google_finance,
}


def normalize(raw, search_no, engine, retrieved_at, id_counter, company, website, category):
    """Dispatches to the normalizer for `engine`. Unknown engines yield []."""
    fn = NORMALIZERS.get(engine)
    if fn is None:
        return []
    try:
        return fn(raw or {}, search_no, engine, retrieved_at, id_counter, company, website, category)
    except (KeyError, TypeError, AttributeError, IndexError):
        return []
