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


def list_exports(database, tenant, app, version, before=None, limit=20):
    events = metadata.tables["application_events"]
    query = select(events).where(
        events.c.application_id == app,
        events.c.version_id == version,
        events.c.action.startswith("index_calls_exported:", autoescape=True),
    )
    if before is not None:
        query = query.where(events.c.id < before)
    with database.read() as db:
        KnowledgeStore.scope(db, tenant, app, version)
        rows = db.execute(query.order_by(events.c.id.desc()).limit(limit + 1)).mappings().all()
    data = []
    for row in rows[:limit]:
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
        data.append(item)
    return {"data": data, "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}
