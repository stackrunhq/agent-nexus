import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app

ADMIN = {"Authorization": "Bearer " + "a" * 32}
CLIENT = {"Authorization": "Bearer " + "c" * 32}


@pytest.fixture
def setup(tmp_path):
    calls = []
    replies = []

    def handle(request):
        calls.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    settings = Settings("a" * 32, "c" * 32, str(tmp_path / "models.db"), {"provider.test"})
    with TestClient(create_app(settings, httpx.MockTransport(handle))) as client:
        yield client, calls, replies, settings


def register(client, provider="openai_compatible", **overrides):
    config = {
        "alias": "help",
        "provider": provider,
        "model": "real-model",
        "base_url": "https://provider.test/v1" if provider != "ollama" else "http://provider.test",
        "deployment": "cloud" if provider != "ollama" else "local",
        "capabilities": ["chat", "embeddings"],
    }
    config.update(overrides)
    return client.put("/api/v1/admin/models/help", headers=ADMIN, json=config)


def chat(client, **overrides):
    body = {"model": "help", "messages": [{"role": "user", "content": "如何使用？"}]}
    body.update(overrides)
    return client.post("/api/v1/chat/completions", headers=CLIENT, json=body)


@pytest.mark.parametrize("provider", ["openai_compatible", "ollama"])
def test_chat_normalization(setup, provider):
    client, calls, replies, _ = setup
    assert register(client, provider).status_code == 200
    replies.append(
        httpx.Response(
            200,
            json=(
                {
                    "message": {"content": "操作说明"},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 8,
                    "eval_count": 3,
                }
                if provider == "ollama"
                else {
                    "choices": [{"message": {"content": "操作说明"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 3},
                }
            ),
        )
    )
    response = chat(client, temperature=0, max_tokens=100)
    assert response.status_code == 200
    result = response.json()
    assert result["content"] == "操作说明"
    assert result["model"] == "help"
    assert result["usage"] == {"input_tokens": 8, "output_tokens": 3}
    assert result["request_id"] == response.headers["x-request-id"]
    sent = json.loads(calls[0].content)
    assert sent["model"] == "real-model" and sent["stream"] is False
    if provider == "ollama":
        assert calls[0].url.path == "/api/chat"
        assert sent["options"] == {"num_predict": 100, "temperature": 0}
    else:
        assert calls[0].url.path == "/v1/chat/completions"
        assert sent["max_tokens"] == 100


@pytest.mark.parametrize("provider", ["openai_compatible", "ollama"])
def test_embeddings_normalization(setup, provider):
    client, calls, replies, _ = setup
    register(client, provider)
    replies.append(
        httpx.Response(
            200,
            json=(
                {"embeddings": [[1, 2], [3, 4]], "prompt_eval_count": 5}
                if provider == "ollama"
                else {
                    "data": [{"index": 1, "embedding": [3, 4]}, {"index": 0, "embedding": [1, 2]}],
                    "usage": {"prompt_tokens": 5},
                }
            ),
        )
    )
    response = client.post(
        "/api/v1/embeddings", headers=CLIENT, json={"model": "help", "input": ["甲", "乙"]}
    )
    assert response.status_code == 200
    assert response.json()["vectors"] == [[1, 2], [3, 4]]
    assert response.json()["dimensions"] == 2
    if provider == "ollama":
        assert json.loads(calls[0].content)["truncate"] is False


def test_auth_and_hidden_config(setup):
    client, _, _, _ = setup
    assert client.get("/api/v1/models").status_code == 401
    assert client.get("/api/v1/admin/models", headers=CLIENT).status_code == 401
    assert client.get("/api/v1/models", headers=ADMIN).status_code == 401
    register(client, api_key_env="NEXUS_PROVIDER_TEST_KEY")
    public = client.get("/api/v1/models", headers=CLIENT).json()
    assert "api_key_env" not in str(public) and "base_url" not in str(public)


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"enabled": False}, 404),
        ({"capabilities": ["embeddings"]}, 422),
        ({"api_key_env": "NEXUS_PROVIDER_MISSING"}, 503),
    ],
)
def test_no_upstream_for_invalid_model(setup, changes, status, monkeypatch):
    monkeypatch.delenv("NEXUS_PROVIDER_MISSING", raising=False)
    client, calls, _, _ = setup
    register(client, **changes)
    assert chat(client).status_code == status
    assert calls == []


@pytest.mark.parametrize(
    "reply,status,code",
    [
        (httpx.Response(429, text="secret"), 429, "provider_rate_limited"),
        (httpx.Response(401, text="secret"), 502, "provider_error"),
        (httpx.Response(302, headers={"Location": "http://untrusted.test"}), 502, "provider_error"),
        (httpx.Response(200, text="secret"), 502, "invalid_provider_response"),
        (httpx.Response(200, json={"choices": []}), 502, "invalid_provider_response"),
        (httpx.ReadTimeout("secret"), 504, "provider_timeout"),
        (httpx.ConnectError("secret"), 502, "provider_unreachable"),
    ],
)
def test_sanitized_errors(setup, reply, status, code):
    client, calls, replies, _ = setup
    register(client)
    replies.append(reply)
    response = chat(client)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "secret" not in response.text
    assert len(calls) == 1  # no silent retry or cloud fallback


def test_validation_and_allowlist(setup):
    client, calls, _, _ = setup
    assert register(client, base_url="https://evil.test/v1").status_code == 403
    assert register(client, base_url="http://provider.test/v1").status_code == 422
    assert register(client, base_url="https://user:secret@provider.test").status_code == 422
    assert register(client, api_key_env="PATH").status_code == 422
    register(client)
    assert chat(client, stream=True).status_code == 422
    assert chat(client, tools=[]).status_code == 422
    assert chat(client, max_tokens=3000).status_code == 422
    assert chat(client, model="missing").status_code == 404
    assert not calls


def test_credentials_forwarded_and_config_persists(setup, monkeypatch):
    client, calls, replies, settings = setup
    monkeypatch.setenv("NEXUS_PROVIDER_TEST_KEY", "provider-secret")
    register(client, api_key_env="NEXUS_PROVIDER_TEST_KEY")
    replies.append(httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
    assert chat(client).status_code == 200
    assert calls[0].headers["Authorization"] == "Bearer provider-secret"
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/v1/models", headers=CLIENT).json()["data"][0]["id"] == "help"
    assert b"provider-secret" not in Path(settings.database_path).read_bytes()


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": []}]},
        {"data": [{"index": 1, "embedding": [1]}]},
        {"data": [{"index": 0, "embedding": [True]}]},
    ],
)
def test_bad_embeddings(setup, payload):
    client, _, replies, _ = setup
    register(client)
    replies.append(httpx.Response(200, json=payload))
    response = client.post(
        "/api/v1/embeddings", headers=CLIENT, json={"model": "help", "input": ["test"]}
    )
    assert response.status_code == 502


def test_fail_closed_startup(tmp_path):
    with (
        pytest.raises(RuntimeError),
        TestClient(create_app(Settings("", "", str(tmp_path / "db"), set()))),
    ):
        pass


def test_admin_test_requires_admin_and_returns_metrics(setup):
    client, calls, replies, _ = setup
    register(client, "ollama")
    path = "/api/v1/admin/models/help/test"
    assert client.post(path, headers=CLIENT, json={}).status_code == 401
    replies.append(httpx.Response(200, json={"done": True, "message": {"content": "OK"}}))
    response = client.post(path, headers=ADMIN, json={"input": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert body["capability"] == "chat"
    assert body["elapsed_ms"] >= 0
    assert body["result"]["content"] == "OK"
    assert body["request_id"] == body["result"]["request_id"]
    assert json.loads(calls[0].content)["messages"][0]["content"] == "你好"


def test_admin_embedding_test_and_disabled_model(setup):
    client, _, replies, _ = setup
    register(client, "ollama", capabilities=["embeddings"])
    path = "/api/v1/admin/models/help/test"
    assert client.post(path, headers=ADMIN, json={"capability": "chat"}).status_code == 422
    replies.append(httpx.Response(200, json={"embeddings": [[0.1, 0.2]]}))
    response = client.post(path, headers=ADMIN, json={"capability": "embeddings"})
    assert response.status_code == 200
    assert response.json()["result"]["dimensions"] == 2
    register(client, enabled=False)
    assert client.post(path, headers=ADMIN, json={}).status_code == 404


def test_token_parameter_and_temperature_capability(setup):
    client, calls, replies, _ = setup
    assert (
        register(
            client, token_parameter="max_completion_tokens", supports_temperature=False
        ).status_code
        == 200
    )
    assert chat(client, temperature=0).status_code == 422
    assert not calls
    replies.append(httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
    assert chat(client, max_tokens=64).status_code == 200
    sent = json.loads(calls[0].content)
    assert sent["max_completion_tokens"] == 64
    assert "max_tokens" not in sent and "temperature" not in sent
    assert register(client, "ollama", token_parameter="max_completion_tokens").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [{"message": []}]},
        {"choices": "wrong"},
        {"choices": [{"message": {"content": "ok"}}], "usage": [1]},
    ],
)
def test_malformed_nested_chat_is_502(setup, payload):
    client, _, replies, _ = setup
    register(client)
    replies.append(httpx.Response(200, json=payload))
    response = chat(client)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_provider_response"


def test_response_size_limit(setup):
    client, _, replies, _ = setup
    register(client)
    replies.append(httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1)))
    response = chat(client)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_response_too_large"


def test_overall_timeout(setup):
    import asyncio

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'{"choices":'
            await asyncio.sleep(2)
            yield b"[]}"

        async def aclose(self):
            self.closed = True

    client, _, replies, _ = setup
    register(client, timeout_seconds=1)
    stream = SlowStream()
    replies.append(httpx.Response(200, stream=stream))
    response = chat(client)
    assert response.status_code == 504
    assert stream.closed


def test_admin_shell_and_settings_security(setup):
    client, _, _, _ = setup
    response = client.get("/admin")
    assert response.status_code == 200
    assert "模型工作台" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    for path in ("admin.js", "admin.css"):
        assert client.get(f"/admin/assets/{path}").status_code == 200
    assert client.get("/api/v1/admin/settings", headers=CLIENT).status_code == 401
    settings = client.get("/api/v1/admin/settings", headers=ADMIN)
    assert settings.json() == {"allowed_hosts": ["provider.test"]}
    assert settings.headers["cache-control"] == "no-store"


def test_old_configuration_gets_compatible_defaults(setup):
    import sqlite3

    client, _, _, settings = setup
    response = register(client)
    legacy = response.json()
    del legacy["token_parameter"]
    del legacy["supports_temperature"]
    with sqlite3.connect(settings.database_path) as db:
        db.execute("UPDATE models SET config = ? WHERE alias = ?", (json.dumps(legacy), "help"))
    with TestClient(create_app(settings)) as restarted:
        config = restarted.get("/api/v1/admin/models", headers=ADMIN).json()[0]
    assert config["token_parameter"] == "max_tokens"
    assert config["supports_temperature"] is True


def test_test_input_validation_does_not_call_provider(setup):
    client, calls, _, _ = setup
    register(client)
    for body in ({"input": " "}, {"input": "x" * 4001}, {"capability": "tools"}):
        assert (
            client.post("/api/v1/admin/models/help/test", headers=ADMIN, json=body).status_code
            == 422
        )
    assert not calls


def test_audit_tracks_changes_without_values_or_noops(setup):
    client, _, _, _ = setup
    created = register(client, api_key_env="NEXUS_PROVIDER_PRIVATE")
    register(client, api_key_env="NEXUS_PROVIDER_PRIVATE")
    register(client, api_key_env="NEXUS_PROVIDER_PRIVATE", enabled=False)
    response = client.get("/api/v1/admin/audit-events", headers=ADMIN)
    assert response.status_code == 200
    events = response.json()["data"]
    assert len(events) == 2
    assert events[0]["action"] == "disabled"
    assert events[0]["changed_fields"] == ["enabled"]
    assert events[1]["action"] == "created"
    assert events[1]["request_id"] == created.headers["x-request-id"]
    assert events[1]["actor"] == "platform_admin"
    assert "NEXUS_PROVIDER_PRIVATE" not in response.text
    assert "provider.test" not in response.text


def test_audit_auth_pagination_and_validation(setup):
    client, _, _, _ = setup
    for enabled in (True, False, True):
        register(client, enabled=enabled)
    path = "/api/v1/admin/audit-events"
    assert client.get(path, headers=CLIENT).status_code == 401
    first = client.get(path, headers=ADMIN, params={"limit": 2}).json()
    assert len(first["data"]) == 2
    second = client.get(
        path, headers=ADMIN, params={"before": first["next_before"], "limit": 2}
    ).json()
    assert len(second["data"]) == 1 and second["next_before"] is None
    assert first["data"][-1]["id"] > second["data"][0]["id"]
    assert client.get(path, headers=ADMIN, params={"alias": "unknown"}).json()["data"] == []
    for params in ({"limit": 0}, {"limit": 101}, {"before": 0}):
        assert client.get(path, headers=ADMIN, params=params).status_code == 422


def test_audit_failure_rolls_back_model_change(setup):
    import sqlite3

    client, _, _, settings = setup
    register(client)
    with sqlite3.connect(settings.database_path) as db:
        db.execute(
            "CREATE TRIGGER reject_audit BEFORE INSERT ON model_audit BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    assert register(client, enabled=False).status_code == 500
    assert client.get("/api/v1/admin/models", headers=ADMIN).json()[0]["enabled"] is True


def test_audit_survives_restart_and_rejected_changes_leave_no_event(setup):
    client, _, _, settings = setup
    register(client)
    assert register(client, base_url="https://untrusted.test").status_code == 403
    with TestClient(create_app(settings)) as restarted:
        events = restarted.get("/api/v1/admin/audit-events", headers=ADMIN).json()["data"]
    assert len(events) == 1
