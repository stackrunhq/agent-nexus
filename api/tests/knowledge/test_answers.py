import json

import httpx
import pytest

from agent_nexus.knowledge.answers import fuse
from agent_nexus.models.schemas import ModelConfig
from test_ingestion import ADMIN, scope as scope
from test_search import publish_catalog
from test_vectors import configure, provider


def prepare(scope, answer=None, callback=None):
    client, tenants, app, version, root, _ = scope
    publish_catalog(client, root)
    model = configure(client)
    chat = ModelConfig(
        alias="chat-local",
        provider="ollama",
        model="chat-v1",
        base_url="http://localhost:11434",
        deployment="local",
        capabilities=["chat"],
    )
    client.app.state.gateway.store.put(chat)
    for alias in (model.alias, chat.alias):
        client.app.state.tenants.grant(tenants[0]["id"], alias, True)
    calls = []

    def transport(request):
        calls.append(request.url.path)
        if request.url.path == "/api/chat":
            if callback:
                callback(client, tenants, root)
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "message": {
                        "content": json.dumps(
                            answer
                            if answer is not None
                            else {"answer": "重置密码 [1]", "citations": ["1"]}
                        )
                    },
                },
            )
        return provider(request)

    client.app.state.gateway.client._transport = httpx.MockTransport(transport)
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 200
    )
    return calls


def test_fusion_deduplicates_and_rewards_agreement():
    a = {"document_id": "a", "chunk_index": 0, "score": 999}
    b = {"document_id": "b", "chunk_index": 0, "score": 0.001}
    result = fuse([[a, b], [b]], 5)
    assert len(result) == 2 and result[0]["document_id"] == "b"


def test_hybrid_and_cited_answer_tenant_boundaries(scope):
    prepare(scope)
    client, tenants, app, version, root, _ = scope
    body = {"model": "embed-local", "query": "password"}
    hybrid = client.post(root + "/hybrid-search", headers=ADMIN, json=body)
    assert hybrid.status_code == 200 and hybrid.json()["method"] == "hybrid_rrf"
    body["chat_model"] = "chat-local"
    public = f"/api/v1/applications/{app['id']}/versions/{version['id']}/answers"
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    result = client.post(public, headers=member, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "answered"
    assert result.json()["citations"][0]["citation_id"] == "1"
    assert "text" in result.json()["citations"][0]
    assert client.post(
        public, headers={"Authorization": "Bearer " + tenants[1]["api_key"]}, json=body
    ).status_code in (403, 404)


@pytest.mark.parametrize(
    "answer",
    [
        {"answer": "invented [99]", "citations": ["99"]},
        {"answer": "no marker", "citations": ["1"]},
        {"answer": "extra [2]", "citations": ["1"]},
        {"answer": 1, "citations": []},
    ],
)
def test_invalid_citations_fail_closed(scope, answer):
    prepare(scope, answer)
    client, _, _, _, root, _ = scope
    result = client.post(
        root + "/answers",
        headers=ADMIN,
        json={"model": "embed-local", "chat_model": "chat-local", "query": "password"},
    )
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "invalid_answer_citations"


def test_uncited_answer_is_refused(scope):
    prepare(scope, {"answer": "unsupported answer", "citations": []})
    client, _, _, _, root, _ = scope
    result = client.post(
        root + "/answers",
        headers=ADMIN,
        json={"model": "embed-local", "chat_model": "chat-local", "query": "password"},
    )
    assert result.json()["status"] == "insufficient_evidence"
    assert "unsupported" not in result.json()["answer"]


def test_inflight_chat_grant_revocation_drops_answer(scope):
    prepare(
        scope,
        callback=lambda client, tenants, root: client.app.state.tenants.grant(
            tenants[0]["id"], "chat-local", False
        ),
    )
    client, _, _, _, root, _ = scope
    result = client.post(
        root + "/answers",
        headers=ADMIN,
        json={"model": "embed-local", "chat_model": "chat-local", "query": "password"},
    )
    assert result.status_code == 403
    assert "answer" not in result.json()


def test_missing_index_does_not_call_chat(scope):
    calls = prepare(scope)
    client, _, _, _, root, _ = scope
    from agent_nexus.knowledge.vectors import indexes

    with client.app.state.knowledge.database.write("test") as db:
        db.execute(indexes.delete())
    result = client.post(
        root + "/answers",
        headers=ADMIN,
        json={"model": "embed-local", "chat_model": "chat-local", "query": "password"},
    )
    assert result.status_code == 409
    assert "/api/chat" not in calls


def test_withdrawal_during_generation_drops_answer(scope):
    def withdraw(client, tenants, root):
        from agent_nexus.knowledge.store import documents

        with client.app.state.knowledge.database.write("test") as db:
            db.execute(documents.update().values(published=0))

    prepare(scope, callback=withdraw)
    client, _, _, _, root, _ = scope
    result = client.post(
        root + "/answers",
        headers=ADMIN,
        json={"model": "embed-local", "chat_model": "chat-local", "query": "password"},
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "index_stale"
