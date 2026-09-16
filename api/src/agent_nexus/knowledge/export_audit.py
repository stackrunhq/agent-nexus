"""Bounded, tenant-scoped view of diagnostic export events."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select

from agent_nexus.storage.database import metadata
from .store import KnowledgeStore


class Filters(BaseModel):
    attempt: Literal["1", "2", "3", "unknown"] | None
    call_status: Literal["pending", "succeeded", "failed"] | None
    call_error: str | None


class Resource(BaseModel):
    tenant_id: str
    app_id: str
    version_id: str
    job_id: str


class ExportRange(BaseModel):
    model_config = ConfigDict(strict=True)
    limit: int
    returned: int
    truncated: bool
    starts_at: int


class Payload(BaseModel):
    format_version: Literal[1]
    outcome: Literal["generated"]
    resource: Resource
    filters: Filters
    export: ExportRange


def list_exports(database, tenant, app, version, before=None, limit=20, job_id=None, actor=None):
    events = metadata.tables["application_events"]
    query = select(events).where(
        events.c.application_id == app,
        events.c.version_id == version,
        events.c.action.startswith("index_calls_exported:", autoescape=True),
    )
    if before is not None:
        query = query.where(events.c.id < before)
    if actor is not None:
        query = query.where(events.c.actor == actor)
    # Legacy task IDs live inside text payloads. Bound parsing instead of scanning
    # unlimited history or relying on database-specific JSON casts of corrupt rows.
    scan_limit = 1000 if job_id is not None else limit
    with database.read() as db:
        KnowledgeStore.scope(db, tenant, app, version)
        rows = db.execute(query.order_by(events.c.id.desc()).limit(scan_limit + 1)).mappings().all()
    data = []
    scanned = 0
    for row in rows[:scan_limit]:
        scanned += 1
        item = {key: row[key] for key in ("id", "actor", "request_id", "created_at")}
        try:
            payload = Payload.model_validate(json.loads(row["action"].split(":", 1)[1]))
            resource = payload.resource
            if (resource.tenant_id, resource.app_id, resource.version_id) != (tenant, app, version):
                raise ValueError("Mismatched resource")
            item.update(payload.model_dump())
            item["readable"] = True
        except (ValueError, ValidationError, TypeError):
            item["readable"] = False
        if job_id is not None and (not item["readable"] or item["resource"]["job_id"] != job_id):
            continue
        data.append(item)
        if len(data) == limit:
            break
    return {
        "data": data,
        "next_cursor": rows[scanned - 1]["id"] if len(rows) > scanned else None,
        "scanned": scanned,
        "scan_limit": scan_limit,
        "filters": {"job_id": job_id, "actor": actor},
    }
