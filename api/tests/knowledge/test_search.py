from agent_nexus.knowledge.jobs import run_once
from agent_nexus.knowledge.search import SearchRequest, tokenize
from test_ingestion import ADMIN, upload, scope as scope


def publish_catalog(client, root):
    first = upload(
        client,
        root,
        "password.txt",
        "重置密码：打开账户设置，选择重置密码。 Reset PASSWORD settings".encode(),
    ).json()
    second = upload(
        client, root, "invoice.txt", "发票管理：在财务页面下载发票。 invoice download".encode()
    ).json()
    hidden = upload(client, root, "hidden.txt", b"unpublished secret password").json()
    while run_once(client.app.state.knowledge):
        pass
    client.patch(root, headers=ADMIN, json={"status": "published"})
    for document in (first, second):
        client.patch(root + "/documents/" + document["id"], headers=ADMIN, json={"published": True})
    return first, second, hidden


def test_lexical_search_sources_isolation_and_withdrawal(scope):
    client, tenants, app, version, root, _ = scope
    first, _, hidden = publish_catalog(client, root)
    public = f"/api/v1/applications/{app['id']}/versions/{version['id']}/search"
    headers = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    response = client.post(public, headers=headers, json={"query": "重置密码"})
    assert response.status_code == 200
    result = response.json()
    assert result["method"] == "lexical_bm25" and result["scanned_chunks"] == 2
    assert result["data"][0]["document_id"] == first["id"]
    assert result["data"][0]["source_kind"] == "document"
    assert result["data"][0]["sha256"] == first["sha256"]
    assert result["data"][0]["version_id"] == version["id"]
    assert hidden["id"] not in str(result)
    assert (
        client.post(
            public,
            headers={"Authorization": "Bearer " + tenants[1]["api_key"]},
            json={"query": "password"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            root.replace(tenants[0]["id"], tenants[1]["id"]) + "/search",
            headers=ADMIN,
            json={"query": "password"},
        ).status_code
        == 404
    )
    assert (
        client.post(public, headers=headers, json={"query": "unrelatedzebra"}).json()["data"] == []
    )
    assert (
        client.post(root + "/search", headers=ADMIN, json={"query": "PASSWORD"}).json()["data"][0][
            "document_id"
        ]
        == first["id"]
    )
    client.patch(root + "/documents/" + first["id"], headers=ADMIN, json={"published": False})
    assert client.post(public, headers=headers, json={"query": "password"}).json()["data"] == []
    client.patch(root, headers=ADMIN, json={"status": "retired"})
    assert client.post(public, headers=headers, json={"query": "invoice"}).status_code == 404


def test_limits_draft_and_disabled_versions(scope, monkeypatch):
    client, tenants, app, _, root, _ = scope
    assert (
        client.post(root + "/search", headers=ADMIN, json={"query": "password"}).status_code == 404
    )
    publish_catalog(client, root)
    for body in (
        {"query": "   "},
        {"query": "%%%？"},
        {"query": "a" * 201},
        {"query": "a", "limit": 21},
        {"query": "a", "tenant_id": "other"},
    ):
        assert client.post(root + "/search", headers=ADMIN, json=body).status_code == 422
    from agent_nexus.knowledge import search

    monkeypatch.setattr(search, "MAX_CHUNKS", 1)
    result = client.post(root + "/search", headers=ADMIN, json={"query": "password"})
    assert result.status_code == 409 and result.json()["error"]["code"] == "search_scope_too_large"
    client.patch(
        f"/api/v1/admin/tenants/{tenants[0]['id']}/applications/{app['id']}",
        headers=ADMIN,
        json={"enabled": False},
    )
    assert (
        client.post(root + "/search", headers=ADMIN, json={"query": "password"}).status_code == 404
    )


def test_normalization_and_determinism(scope):
    client, _, _, _, root, _ = scope
    publish_catalog(client, root)
    assert tokenize("ＰＡＳＳＷＯＲＤ 密码") == ["password", "密", "码", "密码"]
    assert SearchRequest(query=" password ").query == "password"
    results = [
        client.post(
            root + "/search", headers=ADMIN, json={"query": "password 发票", "limit": 2}
        ).json()
        for _ in range(2)
    ]
    assert results[0] == results[1] and len(results[0]["data"]) == 2


def test_bootstrap_search_scope_rejected(tmp_path):
    from fastapi.testclient import TestClient
    from agent_nexus.app import Settings, create_app

    with TestClient(
        create_app(Settings("a" * 32, "b" * 32, str(tmp_path / "boot.db"), set()))
    ) as client:
        response = client.post(
            "/api/v1/applications/a/versions/v/search",
            headers={"Authorization": "Bearer " + "b" * 32},
            json={"query": "password"},
        )
        assert response.status_code == 403
