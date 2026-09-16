"""Whole-task invocation aggregates, independent of the detail page offset."""

from sqlalchemy import select, func, case
from agent_nexus.storage.database import metadata


def summarize(db, tenant, task):
    calls = metadata.tables["model_calls"]
    scope = [
        calls.c.tenant_id == tenant,
        calls.c.model == task["model"],
        calls.c.capability == "embeddings",
    ]
    fields = [calls.c.index_attempt.label("attempt"), func.count().label("calls")]
    for status in ("succeeded", "failed", "pending"):
        fields.append(func.count(case((calls.c.status == status, 1))).label(status))
    for field in ("input_tokens", "output_tokens", "elapsed_ms"):
        fields.extend(
            [
                func.sum(calls.c[field]).label("known_" + field),
                func.count(case((calls.c[field].is_(None), 1))).label(
                    "unknown_" + field + "_calls"
                ),
            ]
        )
    attempts = [
        dict(row)
        for row in db.execute(
            select(*fields)
            .where(*scope, calls.c.index_job_id == task["id"])
            .group_by(calls.c.index_attempt)
            .order_by(calls.c.index_attempt.asc().nulls_last())
        ).mappings()
    ]
    unmatched = db.execute(
        select(func.count())
        .select_from(calls)
        .where(*scope, calls.c.index_job_id.is_(None), calls.c.request_id == task["request_id"])
    ).scalar_one()
    return {
        "attempts": attempts,
        "unconfirmed_request_calls": unmatched,
        "scope": "all_exact_task_calls",
    }
