"""Runs the 16 searches live, exactly once, and writes each raw response to tests/fixtures/.

Usage:
    python scripts/capture_fixtures.py --company "ExampleAI" --website "https://example.ai" \\
        --category "AI legal assistant"

Requires SERPAPI_API_KEY and GROQ_API_KEY in the environment (or .env). Every
request goes through app.serp_client.search, so it is cached and counted against
SEARCH_BUDGET like any other live request. Run this once per development cycle;
all later development reads tests/fixtures/ instead.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import analyzer, planner  # noqa: E402
from app.serp_client import search  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


async def _run(company: str, website: str, category: str) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    print("Wave 1: running searches 1-11...")
    wave1 = planner.plan_wave_1(company, website, category)
    wave1_responses = await asyncio.gather(*[search(p.engine, p.params) for p in wave1])
    for planned, response in zip(wave1, wave1_responses):
        _write_fixture(planned, response.raw, response.status)

    print("Entity call: asking the LLM for competitors and listed comparables...")
    wave1_evidence = []  # capture_fixtures only needs raw responses, not evidence objects
    entities = await analyzer.call_entities(company, website, category, wave1_evidence)
    competitors = entities.get("competitors", [])[:3]
    tickers = [lc.get("ticker", "") for lc in entities.get("listed_companies", [])[:2]]
    print(f"  competitors: {[c.get('name') for c in competitors]}")
    print(f"  tickers: {tickers}")

    print("Wave 2: running searches 12-16...")
    wave2 = planner.plan_wave_2(competitors, tickers)
    wave2_responses = await asyncio.gather(*[search(p.engine, p.params) for p in wave2])
    for planned, response in zip(wave2, wave2_responses):
        _write_fixture(planned, response.raw, response.status)

    print(f"Done. Fixtures written to {FIXTURES_DIR}")


def _write_fixture(planned: planner.PlannedSearch, raw: dict, status: str) -> None:
    path = FIXTURES_DIR / f"search_{planned.no:02d}_{planned.engine}.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"  [{planned.no:02d}] {planned.engine}: {status} -> {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True)
    parser.add_argument("--website", required=True)
    parser.add_argument("--category", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.company, args.website, args.category))


if __name__ == "__main__":
    main()
