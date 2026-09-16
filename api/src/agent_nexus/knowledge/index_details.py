"""Admin task diagnostics without checkpoint payloads or model credentials."""

from sqlalchemy import select, or_, and_
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata
from .index_jobs import jobs, IndexJobs
from .store import KnowledgeStore
from .index_call_summary import summarize


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
            "index_job_id",
            "index_attempt",
            "index_batch_start",
            "index_batch_size",
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
                    or_(
                        calls.c.index_job_id == identifier,
                        and_(
                            calls.c.index_job_id.is_(None), calls.c.request_id == task["request_id"]
                        ),
                    ),
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
            "summary": summarize(db, tenant, task),
            "task": {**IndexJobs.view(task), "request_id": task["request_id"]},
            "calls": {
                "data": [
                    {
                        **dict(row),
                        "association": "exact"
                        if row["index_job_id"] == identifier
                        else "request_match",
                    }
                    for row in rows[:limit]
                ],
                "has_more": len(rows) > limit,
                "offset": offset,
                "limit": limit,
            },
            "correlation": "explicit_task_with_unlinked_request_matches",
        }
