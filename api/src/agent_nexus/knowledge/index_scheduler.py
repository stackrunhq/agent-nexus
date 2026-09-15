"""Index claim ordering; called within the shared index-queue transaction lock."""

import os
from sqlalchemy import case, select
from agent_nexus.storage.database import metadata

state = metadata.tables["knowledge_index_scheduler"]


def strategy():
    value = os.getenv("NEXUS_INDEX_SCHEDULER", "fifo")
    if value not in {"fifo", "tenant_round_robin"}:
        raise RuntimeError("NEXUS_INDEX_SCHEDULER must be fifo or tenant_round_robin")
    return value


def order(db, jobs, mode):
    if mode == "fifo":
        return [jobs.c.created_at, jobs.c.id]
    previous = db.execute(
        select(state.c.last_tenant_id).where(state.c.id == 1)
    ).scalar_one_or_none()
    return [
        case((jobs.c.tenant_id > (previous or ""), 0), else_=1),
        jobs.c.tenant_id,
        jobs.c.created_at,
        jobs.c.id,
    ]


def advance(db, tenant):
    # Same transaction and advisory lock as claiming: restart-safe across workers.
    db.execute(state.delete().where(state.c.id == 1))
    db.execute(state.insert().values(id=1, last_tenant_id=tenant))
