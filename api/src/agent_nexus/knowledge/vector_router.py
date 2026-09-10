from fastapi import APIRouter, Depends, Request, Query
from starlette.concurrency import run_in_threadpool
from agent_nexus.core.errors import GatewayError
from .vectors import IndexRequest, VectorSearchRequest, VectorService


def vector_router(get_store, admin_auth, client_auth):
    router = APIRouter(tags=["Knowledge vectors"])
    admin = "/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}"

    def service(request):
        return VectorService(get_store().database, request.app.state.gateway)

    @router.get(admin + "/vector-index", dependencies=[Depends(admin_auth)])
    async def status(
        tenant_id: str,
        app_id: str,
        version_id: str,
        request: Request,
        model: str = Query(min_length=1, max_length=64),
    ):
        return await run_in_threadpool(
            service(request).describe, tenant_id, app_id, version_id, model
        )

    @router.post(admin + "/vector-index", dependencies=[Depends(admin_auth)])
    async def build(
        tenant_id: str, app_id: str, version_id: str, body: IndexRequest, request: Request
    ):
        return await service(request).build(
            tenant_id, app_id, version_id, body.model, request.state.actor, request.state.request_id
        )

    @router.post(admin + "/vector-search", dependencies=[Depends(admin_auth)])
    async def preview(
        tenant_id: str, app_id: str, version_id: str, body: VectorSearchRequest, request: Request
    ):
        return await service(request).search(
            tenant_id, app_id, version_id, body, request.state.request_id
        )

    @router.post(
        "/api/v1/applications/{app_id}/versions/{version_id}/vector-search",
        dependencies=[Depends(client_auth)],
    )
    async def search(app_id: str, version_id: str, body: VectorSearchRequest, request: Request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return await service(request).search(
            request.state.tenant_id, app_id, version_id, body, request.state.request_id
        )

    return router
