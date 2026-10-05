"""SQLite cache and usage counter, plus saved-briefing JSON files.

Two kinds of persistence live here:
  - the SerpApi response cache and the live-search usage counter, in
    data/pitchscout.db (sqlite3 standard library only)
  - saved briefings, one JSON file per briefing, in saved_briefings/
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SAVED_BRIEFINGS_DIR = BASE_DIR / "saved_briefings"

DB_PATH = DATA_DIR / "pitchscout.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            cache_key TEXT PRIMARY KEY,
            engine TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            live_searches INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO usage (id, live_searches) VALUES (1, 0)"
    )
    conn.commit()
    return conn


def get_cached(cache_key: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT response FROM cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def set_cached(cache_key: str, engine: str, response: dict[str, Any]) -> None:
    conn = _connect()
    try:
        from datetime import datetime, timezone

        conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, engine, response, created_at) "
            "VALUES (?, ?, ?, ?)",
            (cache_key, engine, json.dumps(response), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def increment_usage() -> int:
    conn = _connect()
    try:
        conn.execute("UPDATE usage SET live_searches = live_searches + 1 WHERE id = 1")
        conn.commit()
        row = conn.execute("SELECT live_searches FROM usage WHERE id = 1").fetchone()
        return row[0]
    finally:
        conn.close()


def get_usage() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT live_searches FROM usage WHERE id = 1").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_budget() -> int:
    return int(os.environ.get("SEARCH_BUDGET", "150"))


def save_briefing(briefing: dict[str, Any]) -> None:
    SAVED_BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVED_BRIEFINGS_DIR / f"{briefing['id']}.json"
    path.write_text(json.dumps(briefing, indent=2), encoding="utf-8")


def list_briefings() -> list[dict[str, Any]]:
    SAVED_BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for path in sorted(SAVED_BRIEFINGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "id": data.get("id"),
                "company": data.get("company"),
                "generated_at": data.get("generated_at"),
            }
        )
    out.sort(key=lambda b: b.get("generated_at") or "", reverse=True)
    return out


def get_briefing(briefing_id: str) -> dict[str, Any] | None:
    path = SAVED_BRIEFINGS_DIR / f"{briefing_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find_briefing_by_company(company: str) -> dict[str, Any] | None:
    SAVED_BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    needle = company.strip().lower()
    for path in sorted(SAVED_BRIEFINGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(data.get("company", "")).strip().lower() == needle:
            return data
    return None
