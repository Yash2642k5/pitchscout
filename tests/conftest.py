import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own SQLite db and saved_briefings dir."""
    data_dir = tmp_path / "data"
    saved_dir = tmp_path / "saved_briefings"
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "DB_PATH", data_dir / "pitchscout.db")
    monkeypatch.setattr(storage, "SAVED_BRIEFINGS_DIR", saved_dir)
    monkeypatch.setenv("SEARCH_BUDGET", "150")
    yield


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
