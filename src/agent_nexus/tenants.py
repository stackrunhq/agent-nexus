"""Tenant service credentials and explicit model grants (no user/session system yet)."""

from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

from .schemas import StrictModel


class TenantCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Tenant name cannot be blank")
        return value.strip()


class TenantStatus(StrictModel):
    enabled: bool


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

    return router
