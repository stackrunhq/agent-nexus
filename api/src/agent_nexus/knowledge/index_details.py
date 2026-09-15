"""Admin task diagnostics without checkpoint payloads or model credentials."""

from sqlalchemy import select
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from .index_jobs import jobs, IndexJobs
from .store import KnowledgeStore


def detail(database, tenant, app, version, identifier, offset=0, limit=20):
    calls = metadata.tables["model_calls"]
    with database.read() as db:
        KnowledgeStore.scope(db, tenant, app, version)
        task = (
            db.execute(
                select(jobs).where(
                    jobs.c.id == identifier,
                    jobs.c.tenant_id == tenant,
                    jobs.c.app_id == app,
                    jobs.c.version_id == version,
                )
            )
            .mappings()
            .first()
        )
        if task is None:
            raise GatewayError(404, "index_job_not_found", "Index task does not exist")
        fields = [
            "id",
            "request_id",
            "model",
            "capability",
            "created_at",
            "status",
            "elapsed_ms",
            "input_tokens",
            "output_tokens",
            "error",
        ]
        rows = (
            db.execute(
                select(*(calls.c[field] for field in fields))
                .where(
                    calls.c.tenant_id == tenant,
                    calls.c.request_id == task["request_id"],
                    calls.c.model == task["model"],
                    calls.c.capability == "embeddings",
                )
                .order_by(calls.c.created_at, calls.c.id)
                .offset(offset)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        return {
            "task": {**IndexJobs.view(task), "request_id": task["request_id"]},
            "calls": {
                "data": [dict(row) for row in rows[:limit]],
                "has_more": len(rows) > limit,
                "offset": offset,
                "limit": limit,
            },
            "correlation": "tenant_request_model_capability",
        }
