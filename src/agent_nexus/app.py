import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from .gateway import Gateway, GatewayError
from .schemas import ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse, ModelConfig
from .schemas import Message, ModelTestRequest, ModelTestResponse
from .schemas import ModelView
from .store import ConfigurationConflict, ModelStore
from .tenants import tenant_router
from .tenant_store import TenantStore
from .database import Database


@dataclass
class Settings:
    admin_token: str
    client_token: str
    database_path: str
    allowed_hosts: set[str]
    auth_mode: str = "bootstrap"
    database_url: str | None = None

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("NEXUS_ADMIN_TOKEN", ""),
            os.getenv("NEXUS_CLIENT_TOKEN", ""),
            os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db"),
            {
                h.strip().lower()
                for h in os.getenv(
                    "NEXUS_ALLOWED_HOSTS", "localhost,127.0.0.1,host.docker.internal"
                ).split(",")
                if h.strip()
            },
            os.getenv("NEXUS_AUTH_MODE", "bootstrap"),
            os.getenv("NEXUS_DATABASE_URL") or None,
        )

    def validate(self):
        if self.auth_mode not in {"bootstrap", "tenant"}:
            raise RuntimeError("NEXUS_AUTH_MODE must be bootstrap or tenant")
        if len(self.admin_token) < 32 or (
            self.auth_mode == "bootstrap" and len(self.client_token) < 32
        ):
            raise RuntimeError(
                "Configure separate NEXUS_ADMIN_TOKEN and NEXUS_CLIENT_TOKEN of at least 32 characters"
            )
        if self.admin_token == self.client_token:
            raise RuntimeError("Admin and client tokens must differ")


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        database = Database(settings.database_url or settings.database_path)
        try:
            store = ModelStore(database)
            app.state.tenants = TenantStore(database)
            async with httpx.AsyncClient(
                transport=transport, follow_redirects=False, trust_env=False
            ) as client:
                app.state.gateway = Gateway(store, client, settings.allowed_hosts)
                yield
        finally:
            database.close()

    app = FastAPI(title="Agent Nexus — Model Gateway", version="0.3.0", lifespan=lifespan)
    static_dir = Path(__file__).parent / "static"
    app.mount("/admin/assets", StaticFiles(directory=static_dir), name="admin-assets")
    bearer = HTTPBearer(auto_error=False)

    def admin_auth(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not credentials or not secrets.compare_digest(
            credentials.credentials.encode(), settings.admin_token.encode()
        ):
            raise GatewayError(401, "unauthorized", "Valid administrator token required")

    def client_auth(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if not credentials:
            raise GatewayError(401, "unauthorized", "Valid client token required")
        if settings.auth_mode == "tenant":
            tenant_id = request.app.state.tenants.authenticate(credentials.credentials)
            if tenant_id is None:
                raise GatewayError(401, "unauthorized", "Valid tenant credential required")
            request.state.tenant_id = tenant_id
        else:
            if not secrets.compare_digest(
                credentials.credentials.encode(), settings.client_token.encode()
            ):
                raise GatewayError(401, "unauthorized", "Valid client token required")
            request.state.tenant_id = None

    app.include_router(tenant_router(lambda: app.state.tenants, admin_auth))

    def allowed_models(request: Request):
        if request.state.tenant_id is None:
            return None
        return request.app.state.tenants.allowed(request.state.tenant_id)

    def authorize_model(request: Request, alias: str):
        allowed = allowed_models(request)
        if allowed is not None and alias not in allowed:
            raise GatewayError(403, "model_not_allowed", "Model is not assigned to this tenant")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 -- sanitize unexpected errors at the API boundary
            logging.getLogger(__name__).error(
                "Unhandled request error id=%s", request.state.request_id
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {"code": "internal_error", "message": "Internal server error"},
                    "request_id": request.state.request_id,
                },
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/admin"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'"
            )
        return response

    @app.exception_handler(GatewayError)
    async def gateway_error(request: Request, exc: GatewayError):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("Database request failed id=%s", request.state.request_id)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database operation unavailable",
                },
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo user prompts, credentials or raw validator input.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request; check the API schema",
                    "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],
                },
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "http_error", "message": str(exc.detail)},
                "request_id": request.state.request_id,
            },
        )

    @app.get("/health/live")
    def health():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(request: Request):
        try:
            request.app.state.gateway.store.database.check()
        except (SQLAlchemyError, RuntimeError):
            raise GatewayError(
                503, "database_not_ready", "Database schema or connection is not ready"
            ) from None
        return {"status": "ok"}

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        # Only the static shell is public; all model data requires administrator auth.
        return FileResponse(static_dir / "index.html")

    @app.get("/api/v1/admin/settings", dependencies=[Depends(admin_auth)])
    def admin_settings():
        return {"allowed_hosts": sorted(settings.allowed_hosts), "auth_mode": settings.auth_mode}

    @app.get("/api/v1/admin/audit-events", dependencies=[Depends(admin_auth)])
    def audit_events(
        request: Request,
        alias: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        before: Annotated[int | None, Query(ge=1)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return request.app.state.gateway.store.audit(alias=alias, before=before, limit=limit)

    @app.post(
        "/api/v1/admin/models/{alias}/test",
        dependencies=[Depends(admin_auth)],
        response_model=ModelTestResponse,
    )
    async def test_model(alias: str, body: ModelTestRequest, request: Request):
        gateway = request.app.state.gateway
        start = perf_counter()
        if body.capability == "chat":
            result = await gateway.chat(
                ChatRequest(model=alias, messages=[Message(role="user", content=body.input)]),
                request.state.request_id,
            )
        else:
            result = await gateway.embed(
                EmbeddingRequest(model=alias, input=[body.input]),
                request.state.request_id,
            )
        return ModelTestResponse(
            request_id=request.state.request_id,
            model=alias,
            capability=body.capability,
            elapsed_ms=round((perf_counter() - start) * 1000, 2),
            result=result,
        )

    @app.get(
        "/api/v1/admin/models", dependencies=[Depends(admin_auth)], response_model=list[ModelView]
    )
    def admin_models(request: Request):
        store = request.app.state.gateway.store
        return [{**m.model_dump(), "etag": store.etag(m)} for m in store.list()]

    @app.get(
        "/api/v1/admin/models/{alias}", dependencies=[Depends(admin_auth)], response_model=ModelView
    )
    def get_model(alias: str, request: Request, response: Response):
        store = request.app.state.gateway.store
        config = store.get(alias)
        if config is None:
            raise GatewayError(404, "model_not_found", "Model does not exist")
        response.headers["ETag"] = store.etag(config)
        return {**config.model_dump(), "etag": store.etag(config)}

    @app.put(
        "/api/v1/admin/models/{alias}",
        dependencies=[Depends(admin_auth)],
        response_model=ModelView,
    )
    def put_model(
        alias: str,
        config: ModelConfig,
        request: Request,
        response: Response,
        if_match: Annotated[str | None, Header()] = None,
        if_none_match: Annotated[str | None, Header()] = None,
    ):
        if alias != config.alias:
            raise GatewayError(422, "alias_mismatch", "Path and body aliases must match")
        gateway = request.app.state.gateway
        gateway.check_host(config)
        if if_match is None and if_none_match is None:
            raise GatewayError(
                428,
                "precondition_required",
                "Use If-None-Match: * to create, or If-Match with the saved ETag to update",
            )
        if (
            (if_match is not None and if_none_match is not None)
            or (if_none_match is not None and if_none_match != "*")
            or (
                if_match is not None
                and (
                    len(if_match) != 66
                    or not if_match.startswith('"')
                    or not if_match.endswith('"')
                    or any(c not in "0123456789abcdef" for c in if_match[1:-1])
                )
            )
        ):
            raise GatewayError(
                422, "invalid_precondition", "Supply one exact strong ETag or If-None-Match: *"
            )
        try:
            gateway.store.put(
                config,
                expected_etag=if_match or "*",
                actor="platform_admin",
                request_id=request.state.request_id,
            )
        except ConfigurationConflict:
            raise GatewayError(
                412,
                "configuration_conflict",
                "Configuration changed or alias already exists; reload before saving",
            ) from None
        response.headers["ETag"] = gateway.store.etag(config)
        return {**config.model_dump(), "etag": gateway.store.etag(config)}

    @app.get("/api/v1/models", dependencies=[Depends(client_auth)])
    def models(request: Request):
        allowed = allowed_models(request)
        return {
            "data": [
                {"id": m.alias, "deployment": m.deployment, "capabilities": m.capabilities}
                for m in request.app.state.gateway.store.list()
                if m.enabled and (allowed is None or m.alias in allowed)
            ]
        }

    @app.post(
        "/api/v1/chat/completions", dependencies=[Depends(client_auth)], response_model=ChatResponse
    )
    async def chat(body: ChatRequest, request: Request):
        await run_in_threadpool(authorize_model, request, body.model)
        return await request.app.state.gateway.chat(body, request.state.request_id)

    @app.post(
        "/api/v1/embeddings", dependencies=[Depends(client_auth)], response_model=EmbeddingResponse
    )
    async def embed(body: EmbeddingRequest, request: Request):
        await run_in_threadpool(authorize_model, request, body.model)
        return await request.app.state.gateway.embed(body, request.state.request_id)

    return app
