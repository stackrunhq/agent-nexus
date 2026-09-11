"""Platform administrator endpoints for tenant credentials and model grants."""

from fastapi import APIRouter, Depends, Request, Query
from agent_nexus.models.usage import UsageStore
from .quotas import QuotaPolicy, QuotaStore
from .schemas import TenantCreate, TenantStatus


def tenant_router(get_store, admin_auth):
    router = APIRouter(
        prefix="/api/v1/admin/tenants", tags=["Tenant access"], dependencies=[Depends(admin_auth)]
    )

    @router.post("", status_code=201)
    def create(body: TenantCreate):
        return get_store().create(body.name)

    @router.get("")
    def list_tenants():
        return {"data": get_store().list()}

    @router.patch("/{tenant_id}")
    def set_status(tenant_id: str, body: TenantStatus):
        get_store().status(tenant_id, body.enabled)
        return {"id": tenant_id, "enabled": body.enabled}

    @router.post("/{tenant_id}/rotate-key")
    def rotate(tenant_id: str):
        return get_store().rotate(tenant_id)

    @router.get("/{tenant_id}/models")
    def grants(tenant_id: str):
        return {"data": get_store().grants(tenant_id)}

    @router.put("/{tenant_id}/models/{alias}", status_code=204)
    def grant(tenant_id: str, alias: str):
        get_store().grant(tenant_id, alias, True)

    @router.delete("/{tenant_id}/models/{alias}", status_code=204)
    def revoke(tenant_id: str, alias: str):
        get_store().grant(tenant_id, alias, False)

    @router.get("/{tenant_id}/events")
    def events(tenant_id: str):
        return {"data": get_store().events(tenant_id)}

    @router.get("/{tenant_id}/index-quota")
    def get_quota(tenant_id: str):
        return QuotaStore(get_store().database).get(tenant_id)

    @router.get("/{tenant_id}/model-calls")
    def model_calls(
        tenant_id: str,
        offset: int = Query(default=0, ge=0, le=100000),
        limit: int = Query(default=20, ge=1, le=100),
    ):
        return UsageStore(get_store().database).list(tenant_id, offset, limit)

    @router.get("/{tenant_id}/model-usage")
    def model_usage(tenant_id: str):
        return UsageStore(get_store().database).summary(tenant_id)

    @router.put("/{tenant_id}/index-quota")
    def put_quota(tenant_id: str, body: QuotaPolicy, request: Request):
        return QuotaStore(get_store().database).put(
            tenant_id, body, request.state.actor, request.state.request_id
        )

    return router
