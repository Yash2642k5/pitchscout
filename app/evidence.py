"""Evidence schema: stable IDs, registrable domains, the name filter, and staleness."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

# Second-level public suffixes under which a third label is part of the
# registrable domain (e.g. "example.co.in" not "co.in").
_TWO_LABEL_SUFFIXES = {
    "co.in", "co.uk", "co.jp", "co.kr", "co.nz", "co.za",
    "com.au", "com.br", "com.cn", "com.sg", "com.mx",
    "org.uk", "net.in", "gov.in", "ac.in", "ac.uk", "edu.in",
}


class IdCounter:
    """Generates sequential evidence IDs: e01, e02, ... shared across one run."""

    def __init__(self) -> None:
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"e{self._n:02d}"


def registrable_domain(url: str) -> str:
    """Best-effort registrable domain: strips scheme, www, path, and port."""
    if not url:
        return ""
    netloc = urlparse(url if "//" in url else f"//{url}").netloc or url
    host = netloc.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _TWO_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


_RELATIVE_RE = re.compile(
    r"(\d+)\s+(hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)
_ABSOLUTE_FORMATS = (
    "%Y-%m-%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%d %b %Y",
)


def _try_absolute(date_str: str) -> str | None:
    for fmt in _ABSOLUTE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_date(date_str: str | None, retrieved_at: datetime) -> str | None:
    """Parses a relative ("3 days ago") or absolute date string to an ISO date.

    Returns None when the string is missing or unrecognized.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None

    m = _RELATIVE_RE.search(date_str)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta_days = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        when = retrieved_at - timedelta(days=delta_days)
        return when.date().isoformat()

    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass

    parsed = _try_absolute(date_str)
    if parsed:
        return parsed

    # google_news stamps a time and zone onto the date ("10/01/2026, 08:35 PM, +0000
    # UTC"), which matches none of the date-only formats above. Retry on growing
    # comma-separated prefixes so those items carry a date, and therefore a staleness
    # flag, at all. Growing prefixes rather than the first chunk alone, because
    # "Jul 21, 2026, 07:00 AM" carries a comma inside the date itself.
    chunks = [c.strip() for c in date_str.split(",")]
    for end in range(1, len(chunks)):
        parsed = _try_absolute(", ".join(chunks[:end]))
        if parsed:
            return parsed
    return None


def is_stale(published_date: str | None, retrieved_at: datetime) -> bool:
    if not published_date:
        return False
    try:
        published = datetime.fromisoformat(published_date)
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (retrieved_at - published) > timedelta(days=365)


def passes_name_filter(
    search_no: int, company: str, website: str, title: str, snippet: str, url: str
) -> bool:
    """Searches 1, 2, 5, and 6 keep a result only if it is clearly about the company."""
    if search_no not in (1, 2, 5, 6):
        return True
    haystack = f"{title or ''} {snippet or ''}".lower()
    company_lower = company.lower()
    if company_lower in haystack:
        return True
    
    # Fuzzy match: check if the first word of the company name is in the text
    words = company_lower.split()
    if words and len(words[0]) > 2 and words[0] in haystack:
        return True

    website_domain = registrable_domain(website)
    result_domain = registrable_domain(url)
    return bool(website_domain) and website_domain == result_domain


def build_evidence_item(
    id_counter: IdCounter,
    search_no: int,
    engine: str,
    title: str,
    snippet: str,
    url: str,
    published_date_raw: str | None,
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Builds one schema-valid evidence item."""
    published_date = parse_date(published_date_raw, retrieved_at)
    return {
        "id": id_counter.next_id(),
        "search_no": search_no,
        "engine": engine,
        "title": title or "",
        "snippet": snippet or "",
        "url": url or "",
        "source_domain": registrable_domain(url or ""),
        "published_date": published_date,
        "retrieved_at": retrieved_at.isoformat(),
        "stale": is_stale(published_date, retrieved_at),
    }
