import httpx
import pytest

from app import serp_client, storage


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


class FakeAsyncClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        FakeAsyncClient.calls += 1
        return FakeResponse({"organic_results": [{"title": "Result", "link": "https://x.com", "snippet": "s"}]})


@pytest.fixture(autouse=True)
def reset_fake_client(monkeypatch):
    FakeAsyncClient.calls = 0
    monkeypatch.setattr(serp_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    yield


@pytest.mark.asyncio
async def test_first_call_is_live_and_increments_usage():
    response = await serp_client.search("google", {"q": "Acme AI"})
    assert response.status == "live"
    assert storage.get_usage() == 1
    assert FakeAsyncClient.calls == 1


@pytest.mark.asyncio
async def test_repeating_same_query_hits_cache_and_leaves_usage_unchanged():
    await serp_client.search("google", {"q": "Acme AI"})
    assert storage.get_usage() == 1
    response = await serp_client.search("google", {"q": "Acme AI"})
    assert response.status == "cached"
    assert storage.get_usage() == 1
    assert FakeAsyncClient.calls == 1


@pytest.mark.asyncio
async def test_cache_key_ignores_api_key_and_param_order():
    key_a = serp_client._cache_key("google", {"q": "x", "hl": "en"})
    key_b = serp_client._cache_key("google", {"hl": "en", "q": "x"})
    assert key_a == key_b


@pytest.mark.asyncio
async def test_different_queries_are_different_cache_entries():
    await serp_client.search("google", {"q": "Acme AI"})
    await serp_client.search("google", {"q": "Other Co"})
    assert storage.get_usage() == 2


@pytest.mark.asyncio
async def test_budget_exceeded_raises_before_network_call(monkeypatch):
    monkeypatch.setenv("SEARCH_BUDGET", "1")
    await serp_client.search("google", {"q": "Acme AI"})
    with pytest.raises(serp_client.BudgetExceeded):
        await serp_client.search("google", {"q": "Different query"})
    assert FakeAsyncClient.calls == 1


@pytest.mark.asyncio
async def test_network_error_returns_error_status_without_raising(monkeypatch):
    class RaisingClient(FakeAsyncClient):
        async def get(self, url, params=None):
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(serp_client.httpx, "AsyncClient", RaisingClient)
    response = await serp_client.search("google", {"q": "Acme AI"})
    assert response.status == "error"
    assert response.error is not None
    assert storage.get_usage() == 0
