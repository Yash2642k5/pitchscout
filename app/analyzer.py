"""The two LLM calls: the entity call and the analysis call.

Both calls force a structured JSON response by requiring the model to
invoke a specific tool (submit_entities / submit_briefing) whose
input_schema is the contract. Calls go through Groq's OpenAI-compatible
chat completions API. Neither call is allowed to silently fail: any API
error propagates as AnalyzerError so the caller can record it rather than
fabricate a result.
"""

import asyncio
import json
import os
from typing import Any

import groq

from .prompts import ANALYSIS_TOOL, ENTITY_TOOL, analysis_prompt, entity_prompt

MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 2.0
# Long enough to clear a rolling per-minute token window when Groq gives no hint.
RATE_LIMIT_DELAY_SECONDS = 25.0


class AnalyzerError(Exception):
    """Raised when an LLM call fails or does not return the required tool call."""


def _client() -> groq.AsyncGroq:
    api_key = os.environ.get("GROQ_API_KEY", "")
    return groq.AsyncGroq(api_key=api_key)


def _model() -> str:
    return os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")


def _as_groq_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Converts a {name, description, input_schema} tool into an OpenAI/Groq function tool."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def _coerce_to_schema(value: Any, schema: dict[str, Any]) -> Any:
    """Repairs common type slips (e.g. a list where the schema wants a string) in place.

    Some Groq models occasionally put a list of IDs into a field the schema declares as a
    plain string (most often one named like an evidence field). This walks the value
    alongside its schema and coerces those slips rather than discarding an otherwise-valid
    response over one field's shape.
    """
    schema_type = schema.get("type")
    if schema_type == "object" and isinstance(value, dict):
        props = schema.get("properties", {})
        return {k: (_coerce_to_schema(v, props[k]) if k in props else v) for k, v in value.items()}
    if schema_type == "object" and isinstance(value, str):
        # A bare string where an object (statement, gap, scorecard row, ...) was
        # required. Always return a dict — never the bare string — so every
        # downstream `.get(key, default)` call stays safe regardless of which keys
        # that particular schema uses; the item then reads as empty/missing and is
        # dropped or defaulted by the validator rather than crashing the pipeline.
        props = schema.get("properties", {})
        return {"text": value} if "text" in props else {}
    if schema_type == "array" and isinstance(value, list):
        item_schema = schema.get("items", {})
        return [_coerce_to_schema(v, item_schema) for v in value]
    if schema_type == "array" and isinstance(value, str):
        return [value]
    if schema_type == "string" and isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return value


def _extract_tool_call(message: Any, tool_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    tool_calls = getattr(message, "tool_calls", None) or []
    for call in tool_calls:
        if call.function.name == tool_name:
            try:
                arguments = json.loads(call.function.arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                raise AnalyzerError(f"Model's {tool_name} arguments were not valid JSON.") from exc
            return _coerce_to_schema(arguments, schema)
            
    # Fallback for models that output markdown JSON instead of a tool call
    content = getattr(message, "content", "")
    if content and isinstance(content, str):
        # strip markdown formatting if present
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            arguments = json.loads(cleaned)
            if isinstance(arguments, dict):
                # sometimes models wrap it in {"arguments": {...}} or {"company_summary": [...]}
                if "arguments" in arguments and len(arguments) == 1:
                    arguments = arguments["arguments"]
                return _coerce_to_schema(arguments, schema)
        except json.JSONDecodeError:
            pass

    raise AnalyzerError(f"Model did not call {tool_name}.")


def _repair_tool_use_failure(exc: groq.APIError, tool_name: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Recovers from Groq's strict server-side schema rejection (400 tool_use_failed).

    On that error Groq still includes the model's full attempted generation in
    `body.error.failed_generation`. Rather than throwing away an otherwise-complete
    analysis over one field's type, parse it out and run it through the same coercion
    used on a normal response. Returns None if the body isn't shaped as expected, so the
    caller falls back to raising AnalyzerError as before.
    """
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict) or error.get("code") != "tool_use_failed":
        return None
    failed_generation = error.get("failed_generation")
    if not isinstance(failed_generation, str):
        return None
    try:
        generated = json.loads(failed_generation)
        arguments = generated.get("arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None
    if generated.get("name") != tool_name or not isinstance(arguments, dict):
        return None
    return _coerce_to_schema(arguments, schema)


def _is_rate_limited(exc: groq.APIError) -> bool:
    """True for Groq's per-minute token/request rate limits (needs the window to roll over)."""
    if isinstance(exc, groq.RateLimitError) or getattr(exc, "status_code", None) in (413, 429):
        return True
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    return isinstance(error, dict) and error.get("code") == "rate_limit_exceeded"


def _retry_after_seconds(exc: groq.APIError) -> float | None:
    """Reads Groq's own wait hint, from the retry-after header or the error message."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        for name in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            raw = headers.get(name)
            if not raw:
                continue
            try:
                return float(str(raw).rstrip("s"))
            except ValueError:
                continue
    return None


def _retry_delay_seconds(exc: groq.APIError, attempt: int) -> float:
    # Groq's TPM/RPM limits are rolling per-minute windows: a short backoff won't have
    # freed any budget, so these need a wait close to the window length rather than a
    # quick retry. Groq usually says how long it wants, so prefer its own number and fall
    # back to most of a window. Other failures (a refused tool call, transient capacity)
    # are independent of the last attempt and recover fine on a short exponential backoff.
    if _is_rate_limited(exc):
        hinted = _retry_after_seconds(exc)
        # A hint can come back as 0 on an already-rolled window; keep a floor so a retry
        # never fires into the same exhausted minute it just failed in.
        return max(hinted + 1.0, 8.0) if hinted is not None else RATE_LIMIT_DELAY_SECONDS
    return RETRY_DELAY_SECONDS * (attempt + 1)


async def _call_tool(
    prompt: str,
    tool: dict[str, Any],
    max_tokens: int,
    failure_label: str,
    reasoning_effort: str = "low",
) -> dict[str, Any]:
    """Calls `tool`, retrying a bounded number of times on any Groq API error.

    Empirically, this model sometimes refuses a forced tool call with a prose answer
    instead (a sampling-dependent quirk, not a deterministic failure — the same prompt
    typically succeeds on a later attempt), and Groq's on-demand tier occasionally
    returns transient capacity or per-minute rate-limit errors. Both are worth one or two
    retries before giving up; a real user clicking Generate shouldn't eat a 502 over
    something a retry fixes most of the time.
    """
    tool_name = tool["name"]
    schema = tool["input_schema"]
    last_exc: groq.APIError | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            completion = await _client().chat.completions.create(
                model=_model(),
                max_tokens=max_tokens,
                tools=[_as_groq_tool(tool)],
                tool_choice="required",
                # gpt-oss is a reasoning model: hidden reasoning tokens count against
                # max_tokens, so the budget has to cover both the reasoning and the tool
                # call (at too small a budget Groq returns 400 tool_use_failed with an
                # empty failed_generation). "medium" is what it takes to actually read a
                # pricing figure out of a snippet and rank questions; the callers below
                # size max_tokens to leave room for it. Passed via extra_body because the
                # pinned groq SDK predates the reasoning_effort parameter.
                extra_body={"reasoning_effort": reasoning_effort} if "gpt-oss" in _model() else None,
                messages=[
                    {"role": "system", "content": "You are a specialized JSON data extractor. You must call the provided tool with the requested data. Never output conversational text."},
                    {"role": "user", "content": prompt}
                ],
            )
        except groq.APIError as exc:
            repaired = _repair_tool_use_failure(exc, tool_name, schema)
            if repaired is not None:
                return repaired
            last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(_retry_delay_seconds(exc, attempt))
            continue
        return _extract_tool_call(completion.choices[0].message, tool_name, schema)
    raise AnalyzerError(f"{failure_label} failed after {MAX_ATTEMPTS} attempts: {last_exc}") from last_exc


async def call_entities(
    company: str, website: str, category: str, evidence_items: list[dict]
) -> dict[str, Any]:
    """LLM call 1: exactly three competitors and two listed companies."""
    prompt = entity_prompt(company, website, category, evidence_items)
    return await _call_tool(prompt, ENTITY_TOOL, max_tokens=4000, failure_label="Entity call")


async def call_analysis(
    company: str,
    website: str,
    category: str,
    evidence_items: list[dict],
    role_mix_note: str | None = None,
) -> dict[str, Any]:
    """LLM call 2: overview, market, news, trajectory, commercial, diligence, scorecard."""
    prompt = analysis_prompt(company, website, category, evidence_items, role_mix_note)
    return await _call_tool(
        prompt,
        ANALYSIS_TOOL,
        max_tokens=16000,
        failure_label="Analysis call",
        reasoning_effort="medium",
    )
