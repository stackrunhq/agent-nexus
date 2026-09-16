"""Bounded diagnostic JSON; deliberately excludes prompts and provider configuration."""

import time
from .index_details import detail

EXPORT_LIMIT = 1000


def export(
    database, tenant, app, version, identifier, attempt=None, call_status=None, call_error=None
):
    result = detail(
        database,
        tenant,
        app,
        version,
        identifier,
        limit=EXPORT_LIMIT,
        attempt=attempt,
        call_status=call_status,
        call_error=call_error,
    )
    return {
        "format_version": 1,
        "generated_at": int(time.time()),
        "resource": {
            "tenant_id": tenant,
            "app_id": app,
            "version_id": version,
            "job_id": identifier,
        },
        "filters": {"attempt": attempt, "call_status": call_status, "call_error": call_error},
        "export": {
            "limit": EXPORT_LIMIT,
            "returned": len(result["calls"]["data"]),
            "truncated": result["calls"]["has_more"],
            "starts_at": 0,
        },
        "scope_notes": {
            "calls": "filtered_from_first_page",
            "summary": "all_exact_task_calls",
            "consistency": "live_observations_not_cross_query_snapshot",
            "unknown_values": "null_is_unknown_not_zero",
        },
        **result,
    }
