"""Tenant-specific index admission policy, serialized with task admission."""

import os
from pydantic import Field
from sqlalchemy import select
from agent_nexus.core.schemas import StrictModel
from agent_nexus.storage.database import metadata
from .store import TenantStore

quotas = metadata.tables["tenant_index_quotas"]


class QuotaPolicy(StrictModel):
    daily_limit: int | None = Field(default=None, ge=0, le=100000, strict=True)
    active_limit: int | None = Field(default=None, ge=0, le=100, strict=True)


def policy(db, tenant):
    TenantStore.require(db, tenant)
    row = db.execute(select(quotas).where(quotas.c.tenant_id == tenant)).mappings().first()
    daily = row["daily_limit"] if row else None
    active = row["active_limit"] if row else None
    return {
        "daily_limit": daily,
        "active_limit": active,
        "effective_daily_limit": daily
        if daily is not None
        else int(os.getenv("NEXUS_INDEX_DAILY_LIMIT", "100")),
        "effective_active_limit": active if active is not None else 5,
    }


class QuotaStore:
    def __init__(self, database):
        self.database = database

    def get(self, tenant):
        with self.database.read() as db:
            return policy(db, tenant)

    def put(self, tenant, body, actor, request_id):
        with self.database.write("index-queue") as db:
            TenantStore.require(db, tenant)
            db.execute(quotas.delete().where(quotas.c.tenant_id == tenant))
            db.execute(quotas.insert().values(tenant_id=tenant, **body.model_dump()))
            TenantStore.record(
                db,
                tenant,
                "index_quota_updated",
                alias=(
                    f"actor={actor};request={request_id};daily={body.daily_limit};active={body.active_limit}"
                ),
            )
            return policy(db, tenant)
