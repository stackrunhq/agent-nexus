from types import SimpleNamespace
from agent_nexus.models.usage import UsageStore
from test_ingestion import scope as scope
from test_index_jobs import prepare


def test_totals_preserve_unknown_and_tenant_day_scope(scope, monkeypatch):
    store, alias = prepare(scope)
    client, tenants, _, _, _, _ = scope
    usage = UsageStore(store.database)
    config = client.app.state.gateway.resolve(alias, "embeddings")
    monkeypatch.setattr("agent_nexus.models.usage.time.time", lambda: 86401)
    first = usage.start(tenants[0]["id"], config, "embeddings", "one")
    usage.finish(
        first, 1, result=SimpleNamespace(usage=SimpleNamespace(input_tokens=7, output_tokens=None))
    )
    second = usage.start(tenants[0]["id"], config, "embeddings", "two")
    usage.finish(second, 1, error="provider_timeout")
    usage.start(tenants[0]["id"], config, "embeddings", "three")
    row = usage.summary(tenants[0]["id"])["models"][0]
    assert (row["calls"], row["succeeded"], row["failed"], row["pending"]) == (3, 1, 1, 1)
    assert row["known_input_tokens"] == 7 and row["unknown_input_calls"] == 2
    assert row["known_output_tokens"] is None and row["unknown_output_calls"] == 3
    assert usage.summary(tenants[1]["id"])["models"] == []
    monkeypatch.setattr("agent_nexus.models.usage.time.time", lambda: 172801)
    assert usage.summary(tenants[0]["id"])["models"] == []
