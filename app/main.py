"""FastAPI app and the PitchScout endpoints."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from . import storage  # noqa: E402  (after load_dotenv so env vars are set first)
from .analyzer import AnalyzerError  # noqa: E402
from .pipeline import ValidationError, run_pipeline, run_pipeline_steps  # noqa: E402
from .serp_client import BudgetExceeded  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="PitchScout")


class BriefingRequest(BaseModel):
    company: str = Field(min_length=1)
    website: str = Field(min_length=1)
    category: str = Field(min_length=1)
    gl: str = Field(default="us", pattern=r"^[a-z]{2}$")


def _replay_mode() -> bool:
    return os.environ.get("REPLAY_MODE", "false").strip().lower() == "true"


@app.post("/api/briefing")
async def post_briefing(request: BriefingRequest):
    if _replay_mode():
        briefing = storage.find_briefing_by_company(request.company)
        if briefing is None:
            raise HTTPException(
                status_code=404,
                detail=f"No saved briefing found for '{request.company}' in Replay Mode.",
            )
        return briefing

    try:
        briefing = await run_pipeline(request.company, request.website, request.category, request.gl)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AnalyzerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return briefing


@app.get("/api/briefing/stream")
async def stream_briefing(company: str, website: str, category: str, gl: str = "us"):
    """Server-sent events for a live progress bar. Same pipeline as POST /api/briefing;
    each event is `{"progress": 0-100, "label": str}`, and the last one also carries
    `briefing`. A failure arrives as `{"error": true, "detail": str, "status": int}`.
    """

    async def events():
        if _replay_mode():
            briefing = storage.find_briefing_by_company(company)
            if briefing is None:
                yield _sse(
                    {"error": True, "status": 404, "detail": f"No saved briefing found for '{company}' in Replay Mode."}
                )
                return
            yield _sse({"progress": 100, "label": "Done", "briefing": briefing})
            return

        try:
            async for event in run_pipeline_steps(company, website, category, gl):
                yield _sse(event)
        except ValidationError as exc:
            yield _sse({"error": True, "status": 422, "detail": str(exc)})
        except BudgetExceeded as exc:
            yield _sse({"error": True, "status": 429, "detail": str(exc)})
        except AnalyzerError as exc:
            yield _sse({"error": True, "status": 502, "detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/api/briefings")
async def get_briefings():
    return storage.list_briefings()


@app.get("/api/briefings/{briefing_id}")
async def get_briefing(briefing_id: str):
    briefing = storage.get_briefing(briefing_id)
    if briefing is None:
        raise HTTPException(status_code=404, detail=f"No briefing found with id '{briefing_id}'.")
    return briefing


@app.get("/api/usage")
async def get_usage():
    used = storage.get_usage()
    budget = storage.get_budget()
    return {
        "live_searches": used,
        "budget": budget,
        "remainder": max(budget - used, 0),
        "replay_mode": _replay_mode(),
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
