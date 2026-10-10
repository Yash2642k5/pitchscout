import groq
import httpx
import pytest

from app import analyzer


def _api_error(body):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(400, request=request, json=body)
    return groq.BadRequestError("tool_use_failed", response=response, body=body)


# --- _coerce_to_schema -------------------------------------------------------

def test_coerce_string_field_given_a_list_joins_it():
    schema = {"type": "string"}
    assert analyzer._coerce_to_schema(["a", "b"], schema) == "a; b"


def test_coerce_array_field_given_a_string_wraps_it():
    schema = {"type": "array", "items": {"type": "string"}}
    assert analyzer._coerce_to_schema("solo", schema) == ["solo"]


def test_coerce_object_field_given_a_bare_string_wraps_with_text_key():
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}, "confidence": {"type": "string"}, "evidence": {"type": "array"}},
    }
    assert analyzer._coerce_to_schema("just a sentence", schema) == {"text": "just a sentence"}


def test_coerce_object_field_given_a_string_with_no_text_property_becomes_empty_dict():
    # Regression: a bare string for a gap/scorecard/pricing-row item (none of which have a
    # `text` key) used to pass through unchanged, crashing validator.py's `.get()` calls
    # downstream with AttributeError. It must always come back as a dict.
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    result = analyzer._coerce_to_schema("unrelated", schema)
    assert result == {}
    result.get("name")  # would raise AttributeError if this were still a bare string


def test_coerce_recurses_into_nested_object_and_array():
    schema = {
        "type": "object",
        "properties": {
            "mismatches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"pricing_note": {"type": "string"}, "evidence": {"type": "array"}},
                },
            }
        },
    }
    value = {"mismatches": [{"pricing_note": ["e01", "e03"], "evidence": ["e01"]}]}
    result = analyzer._coerce_to_schema(value, schema)
    assert result == {"mismatches": [{"pricing_note": "e01; e03", "evidence": ["e01"]}]}


def test_coerce_leaves_already_correct_values_untouched():
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    value = {"text": "already fine"}
    assert analyzer._coerce_to_schema(value, schema) == value


# --- _repair_tool_use_failure -------------------------------------------------

def test_repair_extracts_and_coerces_failed_generation():
    body = {
        "error": {
            "code": "tool_use_failed",
            "failed_generation": (
                '{"name": "submit_entities", "arguments": '
                '{"competitors": [], "listed_companies": []}}'
            ),
        }
    }
    exc = _api_error(body)
    result = analyzer._repair_tool_use_failure(exc, "submit_entities", {"type": "object", "properties": {}})
    assert result == {"competitors": [], "listed_companies": []}


def test_repair_returns_none_for_wrong_tool_name():
    body = {
        "error": {
            "code": "tool_use_failed",
            "failed_generation": '{"name": "other_tool", "arguments": {}}',
        }
    }
    exc = _api_error(body)
    assert analyzer._repair_tool_use_failure(exc, "submit_entities", {}) is None


def test_repair_returns_none_for_prose_refusal():
    body = {"error": {"code": "tool_use_failed", "failed_generation": "I don't have enough evidence."}}
    exc = _api_error(body)
    assert analyzer._repair_tool_use_failure(exc, "submit_entities", {}) is None


def test_repair_returns_none_for_unrelated_error_code():
    body = {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}
    exc = _api_error(body)
    assert analyzer._repair_tool_use_failure(exc, "submit_entities", {}) is None


def test_repair_returns_none_when_body_is_not_a_dict():
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(400, request=request, text="not json")
    exc = groq.BadRequestError("boom", response=response, body=None)
    assert analyzer._repair_tool_use_failure(exc, "submit_entities", {}) is None


# --- _call_tool retry behavior -------------------------------------------------

class _FakeToolCallFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name, arguments):
        self.function = _FakeToolCallFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _FakeCompletion:
    def __init__(self, tool_calls):
        self.choices = [type("Choice", (), {"message": _FakeMessage(tool_calls)})()]


TOOL = {
    "name": "submit_entities",
    "description": "test tool",
    "input_schema": {"type": "object", "properties": {"ok": {"type": "string"}}},
}


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    async def instant_sleep(_seconds):
        return None

    monkeypatch.setattr(analyzer.asyncio, "sleep", instant_sleep)
    yield


@pytest.mark.asyncio
async def test_call_tool_succeeds_on_first_try(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    calls["n"] += 1
                    return _FakeCompletion([_FakeToolCall("submit_entities", '{"ok": "yes"}')])

    monkeypatch.setattr(analyzer, "_client", lambda: FakeClient())
    result = await analyzer._call_tool("prompt", TOOL, max_tokens=100, failure_label="Test call")
    assert result == {"ok": "yes"}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_call_tool_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    calls["n"] += 1
                    if calls["n"] < 3:
                        raise _api_error({"error": {"code": "tool_use_failed", "failed_generation": "I refuse."}})
                    return _FakeCompletion([_FakeToolCall("submit_entities", '{"ok": "yes"}')])

    monkeypatch.setattr(analyzer, "_client", lambda: FakeClient())
    result = await analyzer._call_tool("prompt", TOOL, max_tokens=100, failure_label="Test call")
    assert result == {"ok": "yes"}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_call_tool_raises_analyzer_error_after_exhausting_attempts(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    calls["n"] += 1
                    raise _api_error({"error": {"code": "tool_use_failed", "failed_generation": "I refuse."}})

    monkeypatch.setattr(analyzer, "_client", lambda: FakeClient())
    with pytest.raises(analyzer.AnalyzerError):
        await analyzer._call_tool("prompt", TOOL, max_tokens=100, failure_label="Test call")
    assert calls["n"] == analyzer.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_call_tool_uses_repair_path_instead_of_retrying(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    calls["n"] += 1
                    raise _api_error(
                        {
                            "error": {
                                "code": "tool_use_failed",
                                "failed_generation": '{"name": "submit_entities", "arguments": {"ok": ["a", "b"]}}',
                            }
                        }
                    )

    monkeypatch.setattr(analyzer, "_client", lambda: FakeClient())
    result = await analyzer._call_tool("prompt", TOOL, max_tokens=100, failure_label="Test call")
    assert result == {"ok": "a; b"}
    assert calls["n"] == 1

# --- per-minute token budget --------------------------------------------------

def _too_large_error(limit=8000, requested=8208):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    body = {
        "error": {
            "message": (
                "Request too large for model `openai/gpt-oss-120b` ... on tokens per "
                f"minute (TPM): Limit {limit}, Requested {requested}, please reduce your "
                "message size and try again."
            ),
            "type": "tokens",
            "code": "rate_limit_exceeded",
        }
    }
    response = httpx.Response(413, request=request, json=body)
    return groq.APIStatusError("request too large", response=response, body=body)


def test_request_too_large_is_recognised_and_its_limit_read():
    exc = _too_large_error()
    assert analyzer._is_request_too_large(exc) is True
    assert analyzer._reported_token_limit(exc) == 8000


def test_plain_rate_limit_is_not_treated_as_request_too_large():
    body = {"error": {"code": "rate_limit_exceeded", "message": "Rate limit reached, try again in 12s"}}
    assert analyzer._is_request_too_large(_api_error(body)) is False


def test_shrunk_budget_aims_under_the_limit_groq_reported():
    budget = analyzer._shrunk_budget(_too_large_error(), "x" * 27000, 5200)
    assert budget <= 6000
    assert budget < 5200  # always smaller than what was just refused


@pytest.mark.asyncio
async def test_call_tool_rebuilds_a_smaller_prompt_after_413(monkeypatch):
    budgets = []

    def build(budget):
        budgets.append(budget)
        return "prompt " * 100

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    if len(budgets) == 1:
                        raise _too_large_error()
                    return _FakeCompletion([_FakeToolCall("submit_entities", '{"ok": "yes"}')])

    monkeypatch.setattr(analyzer, "_client", lambda: FakeClient())
    result = await analyzer._call_tool(
        build, TOOL, max_tokens=100, failure_label="Test call", token_budget=5200
    )
    assert result == {"ok": "yes"}
    assert len(budgets) == 2
    assert budgets[1] < 5200


def test_token_window_waits_only_when_the_next_call_would_not_fit():
    window = analyzer._TokenWindow()
    assert window.wait_seconds(5000, 8000) == 0.0
    window.record(5000)
    # 5000 spent plus 5000 more is over the 8000 window, so the next call has to wait
    # for the recorded spend to age out.
    assert window.wait_seconds(5000, 8000) > 0
    assert window.wait_seconds(2000, 8000) == 0.0


def test_token_window_does_not_wait_for_a_call_that_can_never_fit():
    window = analyzer._TokenWindow()
    window.record(5000)
    assert window.wait_seconds(9000, 8000) == 0.0
