"""Durable provider invocation records; never store prompts, answers or credentials."""

import time
from uuid import uuid4
from sqlalchemy import select
from agent_nexus.storage.database import metadata
from agent_nexus.tenants.store import TenantStore
from .store import ModelStore

calls = metadata.tables["model_calls"]


class UsageStore:
    def __init__(self, database):
        self.database = database

    def start(self, tenant, config, capability, request_id):
        identifier = str(uuid4())
        with self.database.write("model-usage:" + tenant) as db:
            TenantStore.require(db, tenant)
            db.execute(
                calls.insert().values(
                    id=identifier,
                    tenant_id=tenant,
                    request_id=request_id,
                    model=config.alias,
                    model_fingerprint=ModelStore.etag(config),
                    capability=capability,
                    created_at=int(time.time()),
                    status="pending",
                )
            )
        return identifier

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
