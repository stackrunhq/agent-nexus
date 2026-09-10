"""Enterprise search and administrator preview use identical publication rules."""

from fastapi import APIRouter, Depends, Request

from agent_nexus.core.errors import GatewayError
from .search import SearchRequest, search


def search_router(get_store, admin_auth, client_auth):
    router = APIRouter(tags=["Knowledge search"])

    @router.post(
        "/api/v1/applications/{app_id}/versions/{version_id}/search",
        dependencies=[Depends(client_auth)],
    )
    def public_search(app_id: str, version_id: str, body: SearchRequest, request: Request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return search(get_store().database, request.state.tenant_id, app_id, version_id, body)

    @router.post(
        "/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/search",
        dependencies=[Depends(admin_auth)],
    )
    def preview(tenant_id: str, app_id: str, version_id: str, body: SearchRequest):
        return search(get_store().database, tenant_id, app_id, version_id, body)

    return router
