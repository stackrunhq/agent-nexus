"""Durable provider invocation records; never store prompts, answers or credentials."""

import time
import os
from uuid import uuid4
from sqlalchemy import select, func, case
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from agent_nexus.tenants.store import TenantStore
from .store import ModelStore
from pydantic import Field
from agent_nexus.core.schemas import StrictModel

calls = metadata.tables["model_calls"]
quotas = metadata.tables["tenant_model_quotas"]


class ModelQuotaPolicy(StrictModel):
    daily_limit: int | None = Field(default=None, ge=0, le=1000000, strict=True)


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

    def policy(self, db, tenant):
        TenantStore.require(db, tenant)
        value = db.execute(
            select(quotas.c.daily_limit).where(quotas.c.tenant_id == tenant)
        ).scalar_one_or_none()
        return {
            "daily_limit": value,
            "effective_daily_limit": value if value is not None else daily_limit(),
        }

    def get_policy(self, tenant):
        with self.database.read() as db:
            return self.policy(db, tenant)

    def put_policy(self, tenant, body, actor, request_id):
        with self.database.write("model-usage:" + tenant) as db:
            TenantStore.require(db, tenant)
            db.execute(quotas.delete().where(quotas.c.tenant_id == tenant))
            db.execute(quotas.insert().values(tenant_id=tenant, daily_limit=body.daily_limit))
            TenantStore.record(
                db,
                tenant,
                "model_quota_updated",
                alias=f"actor={actor};request={request_id};daily={body.daily_limit}",
            )
            return self.policy(db, tenant)

    def start(
        self,
        tenant,
        config,
        capability,
        request_id,
        index_job_id=None,
        index_attempt=None,
        index_batch_start=None,
        index_batch_size=None,
    ):
        position = (index_attempt, index_batch_start, index_batch_size)
        if any(value is not None for value in position) and (
            index_job_id is None
            or not all(type(value) is int for value in position)
            or not 1 <= index_attempt <= 3
            or not 0 <= index_batch_start < 128
            or index_batch_start % 16
            or not 1 <= index_batch_size <= 16
            or index_batch_start + index_batch_size > 128
        ):
            raise GatewayError(422, "invalid_index_batch", "Invalid index invocation position")
        identifier = str(uuid4())
        with self.database.write("model-usage:" + tenant) as db:
            TenantStore.require(db, tenant)
            if index_job_id is not None:
                jobs = metadata.tables["knowledge_index_jobs"]
                if (
                    capability != "embeddings"
                    or db.execute(
                        select(jobs.c.id).where(
                            jobs.c.id == index_job_id,
                            jobs.c.tenant_id == tenant,
                            jobs.c.model == config.alias,
                        )
                    ).first()
                    is None
                ):
                    raise GatewayError(422, "invalid_index_job", "Invalid index task association")
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
                    index_job_id=index_job_id,
                    index_attempt=index_attempt,
                    index_batch_start=index_batch_start,
                    index_batch_size=index_batch_size,
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
        return {
            "daily_used": count,
            "daily_limit": self.policy(db, tenant)["effective_daily_limit"],
            "reset_at": start + 86400,
        }

    def summary(self, tenant):
        with self.database.read() as db:
            TenantStore.require(db, tenant)
            now = int(time.time())
            result = self._summary(db, tenant, now)
            result["models"] = [
                dict(row)
                for row in db.execute(
                    select(
                        calls.c.model,
                        calls.c.capability,
                        func.count().label("calls"),
                        func.sum(case((calls.c.status == "succeeded", 1), else_=0)).label(
                            "succeeded"
                        ),
                        func.sum(case((calls.c.status == "failed", 1), else_=0)).label("failed"),
                        func.sum(case((calls.c.status == "pending", 1), else_=0)).label("pending"),
                        func.sum(calls.c.input_tokens).label("known_input_tokens"),
                        func.sum(calls.c.output_tokens).label("known_output_tokens"),
                        func.sum(case((calls.c.input_tokens.is_(None), 1), else_=0)).label(
                            "unknown_input_calls"
                        ),
                        func.sum(case((calls.c.output_tokens.is_(None), 1), else_=0)).label(
                            "unknown_output_calls"
                        ),
                    )
                    .where(calls.c.tenant_id == tenant, calls.c.created_at >= now - now % 86400)
                    .group_by(calls.c.model, calls.c.capability)
                    .order_by(calls.c.model, calls.c.capability)
                ).mappings()
            ]
            result["daily_used"] = sum(row["calls"] for row in result["models"])
            return result

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
