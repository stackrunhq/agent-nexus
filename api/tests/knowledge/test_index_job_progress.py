from agent_nexus.knowledge.index_checkpoints import IndexCheckpoint
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from test_ingestion import ADMIN, scope as scope


def test_progress_api_counts_batches_and_distinguishes_reclaim(scope):
    client, tenants, app, version, root, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    store.enqueue(tenants[0]["id"], app["id"], version["id"], "model", "test", "test")

    def read():
        response = client.get(root + "/index-jobs", headers=ADMIN)
        assert response.status_code == 200
        return response.json()["data"][0]

    assert read()["recovery_state"] == "inactive"
    task = store.claim()
    checkpoint = IndexCheckpoint(store.database, task)
    checkpoint.save("content", "model", [[1, 0]] * 16, 2)
    checkpoint.save("content", "model", [[0, 1]], 2, start=16)
    result = read()
    assert result["saved_batches"] == 2 and result["recovery_state"] == "running"
    assert not {"payload", "claim_token", "lease_until", "content_revision"} & result.keys()
    with store.database.write("test") as db:
        db.execute(jobs.update().where(jobs.c.id == task["id"]).values(lease_until=0))
    assert read()["recovery_state"] == "waiting_for_worker"
    task = store.claim()
    assert read()["recovery_state"] == "retrying" and read()["saved_batches"] == 2
    other = root.replace(tenants[0]["id"], tenants[1]["id"])
    assert client.get(other + "/index-jobs", headers=ADMIN).status_code == 404
    assert client.get(root + "/index-jobs").status_code == 401
    store.fail(task, "test_failure")
    assert read()["saved_batches"] == 0 and read()["recovery_state"] == "inactive"
