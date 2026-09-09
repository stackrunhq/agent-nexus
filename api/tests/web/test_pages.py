from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app
from agent_nexus.web import routes


def test_tenant_page_missing_build_and_scoped_policy(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(routes, "files", lambda _: tmp_path)
    settings = Settings("a" * 32, "b" * 32, str(tmp_path / "test.db"), {"localhost"})
    with TestClient(create_app(settings)) as client:
        assert client.get("/admin/tenants").status_code == 503
        (static / "tenants").mkdir()
        (static / "tenants/index.html").write_text("<html>Enterprise</html>")
        page = client.get("/admin/tenants")
        assert page.status_code == 200
        assert "Enterprise" in page.text
        assert "script-src 'self';" in page.headers["content-security-policy"]
        assert "style-src 'self' 'unsafe-inline';" in page.headers["content-security-policy"]
        assert "'unsafe-inline'" not in client.get("/admin/assets/missing").headers[
            "content-security-policy"
        ]
        assert client.get("/api/v1/admin/tenants").status_code == 401
