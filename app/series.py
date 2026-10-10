"""Chart-ready number series pulled from the raw SerpApi responses.

The normalizers reduce every engine to text evidence, which is what the model
reads. Two engines also carry a plottable series that the text throws away:
google_trends has a 12-month interest timeline, and google_finance has a price
graph. Both are extracted here, straight from the raw response, and ride on the
briefing as `series` so the UI can draw them.

The other two charts in the briefing - industry share and brand value - have no
engine behind them, so they are not built here. Those figures only exist in what
a publisher stated, so they are read off the web and news evidence by the
analysis call and validated like any other claim.

Nothing here raises: a missing or malformed response yields None, and the panel
that would have drawn it falls back to its empty state.
"""

from typing import Any

# A year of weekly trends points is ~53 — small enough to send whole. A finance
# graph can run to several hundred ticks, which is more resolution than the panel
# can show, so it is thinned to this many.
MAX_PRICE_POINTS = 120


def _as_number(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN check


def _thin(points: list[Any], limit: int) -> list[Any]:
    """Evenly samples `points` down to at most `limit`, always keeping the ends."""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    picked = [points[round(i * step)] for i in range(limit)]
    picked[-1] = points[-1]
    return picked


def _short_month(label: str) -> str:
    """"Oct 5 – 11, 2025" -> "Oct 2025". Falls back to the label untouched."""
    text = str(label or "")
    parts = text.rsplit(",", 1)
    if len(parts) != 2:
        return text
    month = parts[0].strip().split()
    year = parts[1].strip()
    if not month or not year.isdigit():
        return text
    return f"{month[0]} {year}"


def _clock(label: str) -> str:
    """"Oct 09 2026, 09:30 AM UTC-04:00" -> "9:30 AM". Falls back to the label."""
    text = str(label or "")
    if "," not in text:
        return text
    tail = text.split(",", 1)[1].strip().split()
    if len(tail) >= 2 and ":" in tail[0]:
        return f"{tail[0].lstrip('0')} {tail[1]}"
    return text


def _day(label: str) -> str:
    """"Oct 09 2026, 09:30 AM UTC-04:00" -> "Oct 09 2026". Falls back to the label."""
    head = str(label or "").split(",", 1)[0].strip().split()
    return " ".join(head[:3]) if len(head) >= 2 else str(label or "")


def _month(label: str) -> str:
    """"Oct 09 2026, 09:30 AM UTC-04:00" -> "Oct 2026". Falls back to the label."""
    head = str(label or "").split(",", 1)[0].strip().split()
    if len(head) >= 3:
        return f"{head[0]} {head[2]}"
    return _day(label)


def extract_trends(raw: dict[str, Any] | None, company: str, category: str) -> dict[str, Any] | None:
    """The 12-month interest-over-time timeline as two 0-100 series.

    Google reports the most recent bucket before the week is over, so its value
    is a partial count that plots as a cliff. Those points are dropped rather
    than drawn as a collapse in interest.
    """
    timeline = ((raw or {}).get("interest_over_time") or {}).get("timeline_data") or []
    usable = [p for p in timeline if isinstance(p, dict) and not p.get("partial_data")]
    if len(usable) < 2:
        return None

    names: list[str] = []
    for point in usable:
        for i, value in enumerate(point.get("values") or []):
            if i >= len(names):
                names.append(str(value.get("query") or ""))

    if not names:
        return None

    def read(point: dict, index: int) -> float:
        values = point.get("values") or []
        if index >= len(values):
            return 0.0
        raw_value = values[index].get("extracted_value", values[index].get("value"))
        return _as_number(raw_value) or 0.0

    series = []
    for index, name in enumerate(names[:2]):
        points = [read(p, index) for p in usable]
        series.append(
            {
                "name": name or (company if index == 0 else category),
                "points": points,
                "average": round(sum(points) / len(points), 1),
                "latest": points[-1],
                "peak": max(points),
            }
        )

    # A series that is flat zero across the whole year is Google telling us the
    # term is below its reporting threshold, not that interest is nil. Plotting
    # it as a line along the axis reads as real data, so it is dropped.
    series = [s for s in series if s["peak"] > 0] or series[:1]

    return {
        "labels": [_short_month(p.get("date")) for p in usable],
        "full_labels": [str(p.get("date") or "") for p in usable],
        "series": series,
        "scale_max": 100,
    }


def _symbol(ticker: Any) -> str:
    """"ACME:NASDAQ" -> "ACME". Google Finance answers with either form."""
    return str(ticker or "").split(":")[0].strip().upper()


def extract_price(raw: dict[str, Any] | None, window: str = "1D") -> dict[str, Any] | None:
    """One ticker's price graph plus the quote that heads it.

    A 1D graph is a tape of intraday ticks, so its points are stamped with a
    clock. Any longer window is a run of daily closes, where the time of day is
    noise: those are stamped with a date, and the axis carries the month.
    """
    data = raw or {}
    graph = [g for g in (data.get("graph") or []) if isinstance(g, dict)]
    summary = data.get("summary") or {}
    intraday = str(window or "1D").upper() == "1D"

    points = []
    for entry in _thin(graph, MAX_PRICE_POINTS):
        price = _as_number(entry.get("price"))
        if price is None:
            continue
        stamp = entry.get("date")
        points.append(
            {
                "label": _clock(stamp) if intraday else _month(stamp),
                "full": _clock(stamp) if intraday else _day(stamp),
                "price": price,
            }
        )

    if len(points) < 2 and not summary:
        return None

    movement = summary.get("price_movement") or {}
    change_pct = _as_number(movement.get("percentage"))
    direction = str(movement.get("movement") or "").lower()
    if direction == "down" and change_pct is not None:
        change_pct = -abs(change_pct)

    prices = [p["price"] for p in points]
    # Over a long window the quote's own movement is the last session's, which
    # says nothing about the line on screen. The window's own change is what the
    # chart shows, so it is computed from the ends of the series.
    window_pct = None
    if not intraday and len(prices) >= 2 and prices[0]:
        window_pct = round(((prices[-1] - prices[0]) / prices[0]) * 100, 2)

    return {
        "name": summary.get("title") or summary.get("stock") or "",
        "stock": summary.get("stock") or "",
        "exchange": summary.get("exchange") or "",
        "currency": summary.get("currency") or "",
        "price": _as_number(summary.get("extracted_price")),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "window": str(window or "1D").upper(),
        "window_pct": window_pct,
        "direction": direction or "flat",
        "points": points,
        "low": min(prices) if prices else None,
        "high": max(prices) if prices else None,
    }


def build_series(
    raw_by_no: dict[int, Any],
    company: str,
    category: str,
    stock_window: str = "1D",
    subject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collects every plottable series in one briefing.

    `raw_by_no` maps a search number to its SerpResponse. Search 9 is trends,
    search 15 is the subject's price graph. `subject` carries who that ticker
    belongs to: the company itself, or the listed stand-in named when the
    company is private.
    """

    def raw_for(no: int) -> dict[str, Any] | None:
        response = raw_by_no.get(no)
        return getattr(response, "raw", None) if response is not None else None

    stock = extract_price(raw_for(15), stock_window)
    if stock and stock["points"]:
        # Whether this line is the company's own is checked, not taken on trust.
        # The ticker comes from a model, and a wrong symbol returns a real graph
        # for the wrong company — which is worse than no graph, because the
        # panel would caption another business's year as this one's.
        asked = _symbol((subject or {}).get("ticker"))
        got = _symbol(stock.get("stock"))
        verified = bool(asked and got and asked == got)
        claimed = bool((subject or {}).get("is_subject"))
        stock.update(
            {
                "is_subject": claimed and verified,
                "unverified": claimed and not verified,
                "stands_in_for": "" if (claimed and verified) else company,
            }
        )
    else:
        stock = None

    return {
        "trends": extract_trends(raw_for(9), company, category),
        "stock": stock,
    }
