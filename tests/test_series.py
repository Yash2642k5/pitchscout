"""The chart series pulled out of raw trends and finance responses."""

from app.series import build_series, extract_price, extract_trends


def _timeline(*rows, partial_last=False):
    """rows: tuples of per-query extracted values for one date bucket."""
    points = []
    for i, values in enumerate(rows):
        point = {
            "date": f"Oct {i + 1} – {i + 7}, 2025",
            "timestamp": str(1759622400 + i * 604800),
            "values": [
                {"query": f"q{j}", "query_index": j, "value": str(v), "extracted_value": v}
                for j, v in enumerate(values)
            ],
        }
        points.append(point)
    if partial_last and points:
        points[-1]["partial_data"] = True
    return {"interest_over_time": {"timeline_data": points}}


class TestExtractTrends:
    def test_returns_one_series_per_query(self):
        out = extract_trends(_timeline((10, 1), (20, 2), (30, 3)), "Co", "cat")
        assert [s["name"] for s in out["series"]] == ["q0", "q1"]
        assert out["series"][0]["points"] == [10, 20, 30]

    def test_summarises_each_series(self):
        out = extract_trends(_timeline((10, 0), (20, 0), (60, 0)), "Co", "cat")
        first = out["series"][0]
        assert first["average"] == 30.0
        assert first["latest"] == 60
        assert first["peak"] == 60

    def test_drops_the_partial_final_bucket(self):
        """Google reports the current week early, so its value is a false cliff."""
        out = extract_trends(_timeline((50,), (50,), (3,), partial_last=True), "Co", "cat")
        assert out["series"][0]["points"] == [50, 50]
        assert len(out["labels"]) == 2

    def test_labels_collapse_to_month_and_year(self):
        out = extract_trends(_timeline((1,), (2,)), "Co", "cat")
        assert out["labels"] == ["Oct 2025", "Oct 2025"]
        assert out["full_labels"][0].startswith("Oct 1")

    def test_drops_a_series_that_never_registers(self):
        """An all-zero series is below Google's reporting floor, not real data."""
        out = extract_trends(_timeline((10, 0), (20, 0)), "Co", "cat")
        assert [s["name"] for s in out["series"]] == ["q0"]

    def test_keeps_a_lone_series_even_at_zero(self):
        out = extract_trends(_timeline((0,), (0,)), "Co", "cat")
        assert len(out["series"]) == 1

    def test_missing_or_short_timelines_yield_none(self):
        assert extract_trends(None, "Co", "cat") is None
        assert extract_trends({}, "Co", "cat") is None
        assert extract_trends(_timeline((5,)), "Co", "cat") is None

    def test_a_malformed_value_counts_as_zero(self):
        raw = _timeline((1,), (2,))
        raw["interest_over_time"]["timeline_data"][1]["values"][0]["extracted_value"] = "n/a"
        out = extract_trends(raw, "Co", "cat")
        assert out["series"][0]["points"] == [1, 0.0]


def _finance(points=3, movement="Up", pct=2.5):
    return {
        "summary": {
            "title": "Example Corp",
            "stock": "EXMP",
            "exchange": "NASDAQ",
            "currency": "USD",
            "extracted_price": 101.5,
            "price_movement": {"percentage": pct, "movement": movement},
        },
        "graph": [
            {"price": 100 + i, "date": f"Oct 09 2026, 09:3{i} AM UTC-04:00", "volume": 10}
            for i in range(points)
        ],
    }


class TestExtractPrice:
    def test_reads_the_quote_and_the_graph(self):
        q = extract_price(_finance())
        assert q["stock"] == "EXMP"
        assert q["exchange"] == "NASDAQ"
        assert q["price"] == 101.5
        assert [p["price"] for p in q["points"]] == [100, 101, 102]

    def test_labels_are_clock_times(self):
        q = extract_price(_finance())
        assert q["points"][0]["label"] == "9:30 AM"

    def test_a_downward_move_is_signed_negative(self):
        """The raw percentage is unsigned; direction lives in a sibling field."""
        q = extract_price(_finance(movement="Down", pct=1.25))
        assert q["change_pct"] == -1.25
        assert q["direction"] == "down"

    def test_session_range_comes_from_the_graph(self):
        q = extract_price(_finance())
        assert q["low"] == 100
        assert q["high"] == 102

    def test_long_graphs_are_thinned_but_keep_both_ends(self):
        q = extract_price(_finance(points=400))
        assert len(q["points"]) == 120
        assert q["points"][0]["price"] == 100
        assert q["points"][-1]["price"] == 499

    def test_empty_response_yields_none(self):
        assert extract_price(None) is None
        assert extract_price({}) is None


class _Resp:
    def __init__(self, raw):
        self.raw = raw


class TestBuildSeries:
    def test_collects_trends_from_search_9_and_prices_from_15_and_16(self):
        out = build_series(
            {9: _Resp(_timeline((10,), (20,))), 15: _Resp(_finance()), 16: _Resp(_finance())},
            "Co",
            "cat",
        )
        assert out["trends"]["series"][0]["points"] == [10, 20]
        assert len(out["prices"]) == 2

    def test_a_failed_search_simply_drops_out(self):
        out = build_series({9: _Resp({}), 15: _Resp({}), 16: _Resp(None)}, "Co", "cat")
        assert out["trends"] is None
        assert out["prices"] == []

    def test_missing_searches_are_not_an_error(self):
        assert build_series({}, "Co", "cat") == {"trends": None, "prices": []}
