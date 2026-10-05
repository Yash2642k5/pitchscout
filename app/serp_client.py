"""The only module that contacts SerpApi. Owns caching and budget rationing.

Caching: the cache key is the SHA-256 hash of the engine plus the sorted
request parameters, excluding api_key. A cache hit costs nothing and never
expires. A cache miss counts against SEARCH_BUDGET; once the live-search
counter reaches the budget, BudgetExceeded is raised before any network
call is attempted.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from . import storage

SERPAPI_URL = "https://serpapi.com/search.json"


class BudgetExceeded(Exception):
    """Raised when a live SerpApi request would exceed SEARCH_BUDGET."""


@dataclass
class SerpResponse:
    engine: str
    params: dict[str, Any]
    status: str  # "live", "cached", or "error"
    raw: dict[str, Any]
    error: str | None = None


def _cache_key(engine: str, params: dict[str, Any]) -> str:
    payload = {"engine": engine, "params": {k: v for k, v in sorted(params.items())}}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def search(engine: str, params: dict[str, Any]) -> SerpResponse:
    """Runs one SerpApi search, through the cache and the budget.

    On any network or API-level failure the error is captured and a
    status of "error" is returned rather than raised, so the pipeline can
    continue. BudgetExceeded is the one exception allowed to propagate.
    """
    cache_key = _cache_key(engine, params)
    cached = storage.get_cached(cache_key)
    if cached is not None:
        return SerpResponse(engine=engine, params=params, status="cached", raw=cached)

    if storage.get_usage() >= storage.get_budget():
        raise BudgetExceeded(
            f"SerpApi search budget of {storage.get_budget()} is spent for this month."
        )

    api_key = os.environ.get("SERPAPI_API_KEY", "")
    request_params = {**params, "engine": engine, "api_key": api_key}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(SERPAPI_URL, params=request_params)
            resp.raise_for_status()
            raw = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return SerpResponse(engine=engine, params=params, status="error", raw={}, error=str(exc))

    if isinstance(raw, dict) and raw.get("error"):
        return SerpResponse(engine=engine, params=params, status="error", raw={}, error=str(raw["error"]))

    storage.increment_usage()
    storage.set_cached(cache_key, engine, raw)
    return SerpResponse(engine=engine, params=params, status="live", raw=raw)
