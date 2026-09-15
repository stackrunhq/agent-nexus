import sqlite3
import pytest
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade


def test_override_zero_reset_and_isolation(scope):
    _, alias = prepare(scope)
    client, tenants, _, _, root, _ = scope
    quota = f"/api/v1/admin/tenants/{tenants[0]['id']}/index-quota"
    assert (
        client.put(quota, headers=ADMIN, json={"daily_limit": 0, "active_limit": 2}).json()[
            "effective_daily_limit"
        ]
        == 0
    )
    assert (
        client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias}).status_code == 429
    )
    other = client.get(
        f"/api/v1/admin/tenants/{tenants[1]['id']}/index-quota", headers=ADMIN
    ).json()
    assert other["daily_limit"] is None
    assert (
        client.put(
            quota, headers=ADMIN, json={"daily_limit": None, "active_limit": None}
        ).status_code
        == 200
    )
    assert (
        client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias}).status_code == 202
    )
    events = client.get(f"/api/v1/admin/tenants/{tenants[0]['id']}/events", headers=ADMIN).json()[
        "data"
    ]
    assert any(event["action"] == "index_quota_updated" for event in events)
    assert client.put(quota, json={"daily_limit": 10}).status_code == 401
    assert client.put(quota, headers=ADMIN, json={"daily_limit": True}).status_code == 422
    assert client.put(quota, headers=ADMIN, json={"active_limit": 101}).status_code == 422
    assert client.get("/api/v1/admin/tenants/missing/index-usage", headers=ADMIN).status_code == 404


def test_0006_explicit_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE tenant_index_quotas")
        db.execute("UPDATE alembic_version SET version_num='0006'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0013"
    database.close()
