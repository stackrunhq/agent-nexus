"""Index worker process observations, separate from task leases."""

import asyncio
from contextlib import asynccontextmanager, suppress
import time
from uuid import uuid4

from sqlalchemy import select, func, case
from starlette.concurrency import run_in_threadpool

from agent_nexus.storage.database import metadata
from .index_scheduler import strategy

workers = metadata.tables["knowledge_index_workers"]
INTERVAL = 10
TTL = 30


def touch(database, identifier):
    now = int(time.time())
    with database.write("worker-presence:" + identifier) as db:
        db.execute(workers.delete().where(workers.c.last_seen < now - 86400))
        db.execute(workers.delete().where(workers.c.id == identifier))
        db.execute(workers.insert().values(id=identifier, strategy=strategy(), last_seen=now))


def remove(database, identifier):
    with database.write("worker-presence:" + identifier) as db:
        db.execute(workers.delete().where(workers.c.id == identifier))


def summary(db, now, api_strategy):
    fresh = (workers.c.last_seen > now - TTL) & (workers.c.last_seen <= now)
    row = (
        db.execute(
            select(
                func.count().label("observed"),
                func.count(case((fresh, 1))).label("recent"),
                func.count(case((fresh & (workers.c.strategy != api_strategy), 1))).label(
                    "mismatched"
                ),
            ).select_from(workers)
        )
        .mappings()
        .one()
    )
    return {
        "recent": row["recent"],
        "stale": row["observed"] - row["recent"],
        "mismatched": row["mismatched"],
        "ttl_seconds": TTL,
        "status": "unknown"
        if not row["recent"]
        else "mismatch"
        if row["mismatched"]
        else "matching",
    }


@asynccontextmanager
async def heartbeat(database):
    identifier = str(uuid4())
    await run_in_threadpool(touch, database, identifier)

    async def pulse():
        while True:
            await asyncio.sleep(INTERVAL)
            await run_in_threadpool(touch, database, identifier)

    task = asyncio.create_task(pulse())
    try:
        yield task
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            try:
                await task
            finally:
                await run_in_threadpool(remove, database, identifier)
