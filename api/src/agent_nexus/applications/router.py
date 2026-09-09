from fastapi import APIRouter, Depends, Request
from agent_nexus.core.errors import GatewayError
from .schemas import ApplicationCreate, ApplicationStatus, VersionCreate, VersionTransition


def application_router(get_store, admin_auth, client_auth):
    router = APIRouter(tags=["Applications and versions"])
    root = "/api/v1/admin/tenants/{tenant_id}/applications"

    @router.get(root, dependencies=[Depends(admin_auth)])
    def list_apps(tenant_id: str):
        return {"data": get_store().list(tenant_id)}

    @router.post(root, dependencies=[Depends(admin_auth)], status_code=201)
    def create(tenant_id: str, body: ApplicationCreate, request: Request):
        return get_store().create(tenant_id, body, request.state.actor, request.state.request_id)

    @router.patch(root + "/{app_id}", dependencies=[Depends(admin_auth)])
    def status(tenant_id: str, app_id: str, body: ApplicationStatus, request: Request):
        return get_store().status(
            tenant_id, app_id, body.enabled, request.state.actor, request.state.request_id
        )

    @router.get(root + "/{app_id}/versions", dependencies=[Depends(admin_auth)])
    def versions(tenant_id: str, app_id: str):
        return {"data": get_store().versions(tenant_id, app_id)}

    @router.post(root + "/{app_id}/versions", dependencies=[Depends(admin_auth)], status_code=201)
    def create_version(tenant_id: str, app_id: str, body: VersionCreate, request: Request):
        return get_store().create_version(
            tenant_id, app_id, body, request.state.actor, request.state.request_id
        )

    @router.patch(root + "/{app_id}/versions/{version_id}", dependencies=[Depends(admin_auth)])
    def transition(
        tenant_id: str, app_id: str, version_id: str, body: VersionTransition, request: Request
    ):
        return get_store().transition(
            tenant_id,
            app_id,
            version_id,
            body.status,
            request.state.actor,
            request.state.request_id,
        )

    @router.get(root + "/{app_id}/events", dependencies=[Depends(admin_auth)])
    def events(tenant_id: str, app_id: str):
        return {"data": get_store().events(tenant_id, app_id)}

    def scope(request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return request.state.tenant_id

    @router.get("/api/v1/applications", dependencies=[Depends(client_auth)])
    def public_apps(request: Request):
        return {"data": get_store().list(scope(request), public=True)}

    @router.get("/api/v1/applications/{app_id}/versions", dependencies=[Depends(client_auth)])
    def public_versions(app_id: str, request: Request):
        return {"data": get_store().versions(scope(request), app_id, public=True)}

    return router
