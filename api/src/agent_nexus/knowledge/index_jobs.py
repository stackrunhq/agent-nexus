"""Persistent index queue with bounded retries and transactional result fencing."""

import time
import uuid
import os
from contextlib import suppress

from sqlalchemy import select, func, or_, and_
from starlette.concurrency import run_in_threadpool

from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from .vectors import VectorService, MAX_INDEX_CHUNKS
from agent_nexus.tenants.quotas import policy
from .index_checkpoints import IndexCheckpoint, clear

jobs = metadata.tables["knowledge_index_jobs"]


class IndexJobs:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def view(row):
        return {
            key: row[key] for key in ("id", "model", "status", "attempts", "created_at", "error")
        }

    def usage(self, tenant):
        with self.database.read() as db:
            return self._usage(db, tenant)

    def _usage(self, db, tenant, now=None):
        now = int(time.time()) if now is None else now
        day_start = now - now % 86400
        limit = int(os.getenv("NEXUS_INDEX_DAILY_LIMIT", "100"))
        if not 1 <= limit <= 100000:
            raise ValueError("NEXUS_INDEX_DAILY_LIMIT must be 1..100000")
        limits = policy(db, tenant)
        limit = limits["effective_daily_limit"]
        used = db.execute(
            select(func.count())
            .select_from(jobs)
            .where(jobs.c.tenant_id == tenant, jobs.c.created_at >= day_start)
        ).scalar_one()
        active = db.execute(
            select(func.count())
            .select_from(jobs)
            .where(jobs.c.tenant_id == tenant, jobs.c.status.in_(["queued", "processing"]))
        ).scalar_one()
        return {
            "daily_limit": limit,
            "daily_used": used,
            "reset_at": day_start + 86400,
            "active": active,
            "active_limit": limits["effective_active_limit"],
        }

    def enqueue(self, tenant, app, version, model, actor, request_id, *, immediate=False):
        with self.database.write("index-queue") as db:
            active = jobs.c.status.in_(["queued", "processing"])
            existing = (
                db.execute(
                    select(jobs).where(jobs.c.version_id == version, jobs.c.model == model, active)
                )
                .mappings()
                .first()
            )
            if existing:
                if immediate:
                    raise GatewayError(409, "index_job_active", "An index task is already active")
                return self.view(existing)
            now = int(time.time())
            usage = self._usage(db, tenant, now)
            if usage["active"] >= usage["active_limit"]:
                raise GatewayError(
                    429, "index_queue_full", "Tenant active index task limit reached"
                )
            if usage["daily_used"] >= usage["daily_limit"]:
                raise GatewayError(
                    429, "index_daily_quota_exceeded", "Tenant daily index quota exceeded"
                )
            row = dict(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                app_id=app,
                version_id=version,
                model=model,
                actor=actor,
                request_id=request_id,
                status="processing" if immediate else "queued",
                attempts=1 if immediate else 0,
                lease_until=now + 300 if immediate else 0,
                claim_token=str(uuid.uuid4()) if immediate else "",
                created_at=now,
                error=None,
            )
            db.execute(jobs.insert().values(**row))
            return row if immediate else self.view(row)

    def fail(self, task, error):
        with self.database.write("index-queue") as db:
            self.finish(db, task, error)

    def list(self, tenant, app, version):
        with self.database.read() as db:
            return {
                "data": [
                    self.view(row)
                    for row in db.execute(
                        select(jobs)
                        .where(
                            jobs.c.tenant_id == tenant,
                            jobs.c.app_id == app,
                            jobs.c.version_id == version,
                        )
                        .order_by(jobs.c.created_at.desc(), jobs.c.id)
                        .limit(20)
                    ).mappings()
                ]
            }

    def claim(self):
        now = int(time.time())
        with self.database.write("index-queue") as db:
            expired = and_(jobs.c.status == "processing", jobs.c.lease_until <= now)
            db.execute(
                jobs.update()
                .where(expired, jobs.c.attempts >= 3)
                .values(status="failed", error="worker_interrupted", claim_token="", lease_until=0)
            )
            clear(db, select(jobs.c.id).where(jobs.c.status.in_(["failed", "succeeded"])))
            row = (
                db.execute(
                    select(jobs)
                    .where(or_(jobs.c.status == "queued", expired))
                    .order_by(jobs.c.created_at, jobs.c.id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            task = {
                **row,
                "status": "processing",
                "attempts": row["attempts"] + 1,
                "claim_token": str(uuid.uuid4()),
                "lease_until": now + 300,
            }
            db.execute(jobs.update().where(jobs.c.id == task["id"]).values(**task))
            return task

    def finish(self, db, task, error=None):
        result = db.execute(
            jobs.update()
            .where(
                jobs.c.id == task["id"],
                jobs.c.status == "processing",
                jobs.c.claim_token == task["claim_token"],
                jobs.c.lease_until > int(time.time()),
            )
            .values(
                status="failed" if error else "succeeded",
                error=error,
                claim_token="",
                lease_until=0,
            )
        )
        if result.rowcount != 1:
            raise GatewayError(409, "index_lease_lost", "Index worker lease is no longer valid")
        clear(db, [task["id"]])


async def run_once(database, gateway):
    store = IndexJobs(database)
    task = await run_in_threadpool(store.claim)
    if task is None:
        return False
    try:
        await VectorService(database, gateway).build(
            task["tenant_id"],
            task["app_id"],
            task["version_id"],
            task["model"],
            task["actor"],
            task["request_id"],
            on_save=lambda db: store.finish(db, task),
            checkpoint=IndexCheckpoint(database, task),
        )
    except Exception as exc:
        error = exc.code if isinstance(exc, GatewayError) else "index_worker_failed"

        def fail():
            with database.write("index-queue") as db:
                store.finish(db, task, error)

        with suppress(GatewayError):
            await run_in_threadpool(fail)
    return True


def validate_submission(service, tenant, app, version, model):
    rows, _ = service.snapshot(tenant, app, version, model)
    if not rows or len(rows) > MAX_INDEX_CHUNKS:
        raise GatewayError(409, "index_capacity", "Indexing requires 1..128 published chunks")
