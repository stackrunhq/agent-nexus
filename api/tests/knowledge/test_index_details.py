from agent_nexus.knowledge.index_jobs import IndexJobs
from agent_nexus.storage.database import metadata
from test_ingestion import ADMIN, scope as scope


def test_details_scope_correlation_paging_and_redaction(scope):
    client, tenants, app, version, _, _ = scope
    database = client.app.state.knowledge.database
    task = IndexJobs(database).enqueue(
        tenants[0]["id"], app["id"], version["id"], "local", "actor", "same-request"
    )
    calls = metadata.tables["model_calls"]
    with database.write("test") as db:
        for i in range(5):
            db.execute(
                calls.insert().values(
                    id=str(i),
                    tenant_id=tenants[1]["id"] if i == 2 else tenants[0]["id"],
                    request_id="different" if i == 3 else "same-request",
                    model="local",
                    model_fingerprint="private",
                    capability="chat" if i == 4 else "embeddings",
                    created_at=i,
                    status="pending",
                )
            )
    root = f"/api/v1/admin/tenants/{tenants[0]['id']}/applications/{app['id']}/versions/{version['id']}/index-jobs/{task['id']}"
    result = client.get(root, headers=ADMIN, params={"limit": 1}).json()
    assert result["task"]["request_id"] == "same-request"
    assert result["calls"]["has_more"] and result["calls"]["data"][0]["id"] == "0"
    assert (
        "claim_token" not in result["task"]
        and "model_fingerprint" not in result["calls"]["data"][0]
    )
    result = client.get(root, headers=ADMIN, params={"limit": 1, "offset": 1}).json()
    assert result["calls"]["data"][0]["id"] == "1" and not result["calls"]["has_more"]
    assert client.get(root).status_code == 401
    assert (
        client.get(root.replace(tenants[0]["id"], tenants[1]["id"]), headers=ADMIN).status_code
        == 404
    )
    assert client.get(root + "missing", headers=ADMIN).status_code == 404
    assert client.get(root, headers=ADMIN, params={"offset": -1}).status_code == 422
