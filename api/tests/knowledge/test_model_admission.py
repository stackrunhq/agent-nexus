from concurrent.futures import ThreadPoolExecutor
import httpx
from agent_nexus.models.usage import UsageStore
from agent_nexus.core.errors import GatewayError
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare


def test_quota_blocks_upstream_and_shared_index(scope, monkeypatch):
    store, alias = prepare(scope)
    client, tenants, _, _, root, _ = scope
    monkeypatch.setenv("NEXUS_MODEL_DAILY_LIMIT", "1")
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"embeddings": [[1, 0]]})

    client.app.state.gateway.client._transport = httpx.MockTransport(provider)
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["x"]}
        ).status_code
        == 200
    )
    result = client.post(root + "/vector-index", headers=ADMIN, json={"model": alias})
    assert (
        result.status_code == 429 and result.json()["error"]["code"] == "model_daily_quota_exceeded"
    )
    assert len(calls) == 1
    assert UsageStore(store.database).summary(tenants[0]["id"])["daily_used"] == 1


def test_concurrency_pending_and_rollover(scope, monkeypatch):
    store, alias = prepare(scope)
    client, tenants, _, _, _, _ = scope
    monkeypatch.setenv("NEXUS_MODEL_DAILY_LIMIT", "2")
    monkeypatch.setattr("agent_nexus.models.usage.time.time", lambda: 86401)
    usage = UsageStore(store.database)
    config = client.app.state.gateway.resolve(alias, "embeddings")

    def attempt(i):
        try:
            usage.start(tenants[0]["id"], config, "embeddings", str(i))
            return 1
        except GatewayError as error:
            assert error.code == "model_daily_quota_exceeded"
            return 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8))) == 2
    assert usage.summary(tenants[1]["id"])["daily_used"] == 0
    monkeypatch.setattr("agent_nexus.models.usage.time.time", lambda: 172801)
    assert usage.summary(tenants[0]["id"])["daily_used"] == 0
    assert attempt(9) == 1
