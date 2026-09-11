"""Durable provider invocation records; never store prompts, answers or credentials."""

import time
import os
from uuid import uuid4
from sqlalchemy import select, func
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from agent_nexus.tenants.store import TenantStore
from .store import ModelStore

calls = metadata.tables["model_calls"]


def daily_limit():
    try:
        value = int(os.getenv("NEXUS_MODEL_DAILY_LIMIT", "1000"))
        if not 0 <= value <= 1000000:
            raise ValueError()
        return value
    except ValueError:
        raise RuntimeError("NEXUS_MODEL_DAILY_LIMIT must be an integer in 0..1000000") from None


class UsageStore:
    def __init__(self, database):
        self.database = database

    def start(self, tenant, config, capability, request_id):
        identifier = str(uuid4())
        with self.database.write("model-usage:" + tenant) as db:
            TenantStore.require(db, tenant)
            now = int(time.time())
            usage = self._summary(db, tenant, now)
            if usage["daily_used"] >= usage["daily_limit"]:
                raise GatewayError(
                    429,
                    "model_daily_quota_exceeded",
                    "Tenant daily model invocation quota exceeded",
                )
            db.execute(
                calls.insert().values(
                    id=identifier,
                    tenant_id=tenant,
                    request_id=request_id,
                    model=config.alias,
                    model_fingerprint=ModelStore.etag(config),
                    capability=capability,
                    created_at=now,
                    status="pending",
                )
            )
        return identifier

    def _summary(self, db, tenant, now):
        start = now - now % 86400
        count = db.execute(
            select(func.count())
            .select_from(calls)
            .where(calls.c.tenant_id == tenant, calls.c.created_at >= start)
        ).scalar_one()
        return {"daily_used": count, "daily_limit": daily_limit(), "reset_at": start + 86400}

    def summary(self, tenant):
        with self.database.read() as db:
            TenantStore.require(db, tenant)
            return self._summary(db, tenant, int(time.time()))

    def finish(self, identifier, elapsed_ms, result=None, error=None):
        with self.database.write("model-call:" + identifier) as db:
            db.execute(
                calls.update()
                .where(calls.c.id == identifier, calls.c.status == "pending")
                .values(
                    status="failed" if error else "succeeded",
                    elapsed_ms=elapsed_ms,
                    error=error,
                    input_tokens=result.usage.input_tokens if result else None,
                    output_tokens=result.usage.output_tokens if result else None,
                )
            )

    def list(self, tenant, offset=0, limit=20):
        with self.database.read() as db:
            TenantStore.require(db, tenant)
            return {
                "data": [
                    dict(row)
                    for row in db.execute(
                        select(calls)
                        .where(calls.c.tenant_id == tenant)
                        .order_by(calls.c.created_at.desc(), calls.c.id)
                        .offset(offset)
                        .limit(limit)
                    ).mappings()
                ]
            }
