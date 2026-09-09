from typing import Annotated
from time import perf_counter
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from agent_nexus.core.errors import GatewayError
from .schemas import (
    ChatRequest,
    EmbeddingRequest,
    Message,
    ModelConfig,
    ModelTestRequest,
    ModelTestResponse,
    ModelView,
)
from .store import ConfigurationConflict


def admin_model_router(settings, admin_auth):
    router = APIRouter(tags=["Model administration"])

    @router.get("/api/v1/admin/settings", dependencies=[Depends(admin_auth)])
    def admin_settings():
        return {"allowed_hosts": sorted(settings.allowed_hosts), "auth_mode": settings.auth_mode}

    @router.get("/api/v1/admin/audit-events", dependencies=[Depends(admin_auth)])
    def audit_events(
        request: Request,
        alias: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        before: Annotated[int | None, Query(ge=1)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return request.app.state.gateway.store.audit(alias=alias, before=before, limit=limit)

    @router.post(
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

    @router.get(
        "/api/v1/admin/models", dependencies=[Depends(admin_auth)], response_model=list[ModelView]
    )
    def admin_models(request: Request):
        store = request.app.state.gateway.store
        return [{**m.model_dump(), "etag": store.etag(m)} for m in store.list()]

    @router.get(
        "/api/v1/admin/models/{alias}", dependencies=[Depends(admin_auth)], response_model=ModelView
    )
    def get_model(alias: str, request: Request, response: Response):
        store = request.app.state.gateway.store
        config = store.get(alias)
        if config is None:
            raise GatewayError(404, "model_not_found", "Model does not exist")
        response.headers["ETag"] = store.etag(config)
        return {**config.model_dump(), "etag": store.etag(config)}

    @router.put(
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
                actor=request.state.actor,
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

    return router
