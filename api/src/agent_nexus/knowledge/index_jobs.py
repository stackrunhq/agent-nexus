"""Persistent index queue with bounded retries and transactional result fencing."""

import time
import uuid
from contextlib import suppress

from sqlalchemy import select, func, or_, and_
from starlette.concurrency import run_in_threadpool

from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from .vectors import VectorService, MAX_INDEX_CHUNKS

jobs = metadata.tables["knowledge_index_jobs"]


class IndexJobs:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def view(row):
        return {
            key: row[key] for key in ("id", "model", "status", "attempts", "created_at", "error")
        }

    def enqueue(self, tenant, app, version, model, actor, request_id):
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
                return self.view(existing)
            count = db.execute(
                select(func.count()).select_from(jobs).where(jobs.c.tenant_id == tenant, active)
            ).scalar_one()
            if count >= 5:
                raise GatewayError(429, "index_queue_full", "Tenant has five active index tasks")
            row = dict(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                app_id=app,
                version_id=version,
                model=model,
                actor=actor,
                request_id=request_id,
                status="queued",
                attempts=0,
                lease_until=0,
                claim_token="",
                created_at=int(time.time()),
                error=None,
            )
            db.execute(jobs.insert().values(**row))
            return self.view(row)

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
