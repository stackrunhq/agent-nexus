import hashlib
import json

import httpx
import pytest

from agent_nexus.knowledge.jobs import run_once
from agent_nexus.knowledge.vectors import fingerprint, indexes, index_metadata
from test_ingestion import ADMIN, upload, scope as scope
from test_vectors import configure, provider


def test_fingerprint_retains_persisted_format():
    for rows in ([], [{"text": '中文\n"\\', "nested": [None, True, 1.25]}]):
        old = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=True).encode())
        assert fingerprint(rows) == old.hexdigest()


@pytest.mark.parametrize("change", ["withdraw", "revoke", "model"])
def test_batch_change_stops_calls_and_preserves_previous_index(scope, change):
    client, tenants, app, version, root, _ = scope
    document = upload(client, root, "large.txt", ("password settings " * 1800).encode()).json()
    while run_once(client.app.state.knowledge):
        pass
    assert client.patch(root, headers=ADMIN, json={"status": "published"}).status_code == 200
    assert (
        client.patch(
            root + "/documents/" + document["id"], headers=ADMIN, json={"published": True}
        ).status_code
        == 200
    )
    model = configure(client)
    tenant = tenants[0]["id"]
    client.app.state.tenants.grant(tenant, model.alias, True)
    calls = []
    mutate = False

    def upstream(request):
        calls.append(len(json.loads(request.content)["input"]))
        if mutate:
            if change == "withdraw":
                client.app.state.knowledge.publish(
                    tenant, app["id"], version["id"], document["id"], False, "test", "test"
                )
            elif change == "revoke":
                client.app.state.tenants.grant(tenant, model.alias, False)
            else:
                client.app.state.gateway.store.put(
                    model.model_copy(update={"model": "changed"}),
                    expected_etag=client.app.state.gateway.store.etag(model),
                )
        return provider(request)

    client.app.state.gateway.client._transport = httpx.MockTransport(upstream)
    result = client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias})
    assert result.status_code == 200
    assert len(calls) >= 2 and max(calls) == 16 and sum(calls) == result.json()["chunks"]
    database = client.app.state.knowledge.database
    with database.read() as db:
        before = tuple(
            dict(db.execute(table.select()).mappings().one()) for table in (indexes, index_metadata)
        )
    calls.clear()
    mutate = True
    failed = client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias})
    assert failed.status_code == (403 if change == "revoke" else 409)
    assert calls == [16]
    with database.read() as db:
        after = tuple(
            dict(db.execute(table.select()).mappings().one()) for table in (indexes, index_metadata)
        )
    assert after == before
