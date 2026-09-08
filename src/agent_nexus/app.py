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
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from .gateway import Gateway, GatewayError
from .schemas import ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse, ModelConfig
from .schemas import Message, ModelTestRequest, ModelTestResponse
from .store import ModelStore


@dataclass
class Settings:
    admin_token: str
    client_token: str
    database_path: str
    allowed_hosts: set[str]

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
        )

    def validate(self):
        if min(len(self.admin_token), len(self.client_token)) < 32:
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
        store = ModelStore(settings.database_path)
        async with httpx.AsyncClient(
            transport=transport, follow_redirects=False, trust_env=False
        ) as client:
            app.state.gateway = Gateway(store, client, settings.allowed_hosts)
            yield

    app = FastAPI(title="Agent Nexus — Model Gateway", version="0.2.0", lifespan=lifespan)
    static_dir = Path(__file__).parent / "static"
    app.mount("/admin/assets", StaticFiles(directory=static_dir), name="admin-assets")
    bearer = HTTPBearer(auto_error=False)

    def admin_auth(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not credentials or not secrets.compare_digest(
            credentials.credentials.encode(), settings.admin_token.encode()
        ):
            raise GatewayError(401, "unauthorized", "Valid administrator token required")

    def client_auth(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not credentials or not secrets.compare_digest(
            credentials.credentials.encode(), settings.client_token.encode()
        ):
            raise GatewayError(401, "unauthorized", "Valid client token required")

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
        request.app.state.gateway.store.list()
        return {"status": "ok"}

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        # Only the static shell is public; all model data requires administrator auth.
        return FileResponse(static_dir / "index.html")

    @app.get("/api/v1/admin/settings", dependencies=[Depends(admin_auth)])
    def admin_settings():
        return {"allowed_hosts": sorted(settings.allowed_hosts)}

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
        "/api/v1/admin/models", dependencies=[Depends(admin_auth)], response_model=list[ModelConfig]
    )
    def admin_models(request: Request):
        return request.app.state.gateway.store.list()

    @app.put(
        "/api/v1/admin/models/{alias}",
        dependencies=[Depends(admin_auth)],
        response_model=ModelConfig,
    )
    def put_model(alias: str, config: ModelConfig, request: Request):
        if alias != config.alias:
            raise GatewayError(422, "alias_mismatch", "Path and body aliases must match")
        gateway = request.app.state.gateway
        gateway.check_host(config)
        gateway.store.put(config)
        return config

    @app.get("/api/v1/models", dependencies=[Depends(client_auth)])
    def models(request: Request):
        return {
            "data": [
                {"id": m.alias, "deployment": m.deployment, "capabilities": m.capabilities}
                for m in request.app.state.gateway.store.list()
                if m.enabled
            ]
        }

    @app.post(
        "/api/v1/chat/completions", dependencies=[Depends(client_auth)], response_model=ChatResponse
    )
    async def chat(body: ChatRequest, request: Request):
        return await request.app.state.gateway.chat(body, request.state.request_id)

    @app.post(
        "/api/v1/embeddings", dependencies=[Depends(client_auth)], response_model=EmbeddingResponse
    )
    async def embed(body: EmbeddingRequest, request: Request):
        return await request.app.state.gateway.embed(body, request.state.request_id)

    return app
