"""Actual history queries and PostgreSQL plans in a disposable database."""

import argparse
import json
import os
from pathlib import Path
import statistics
import time

from sqlalchemy import event, text
from agent_nexus.storage.database import Database, metadata
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from agent_nexus.knowledge.index_cursor import encode, scope_key
from agent_nexus_cli.database import upgrade
from agent_nexus_cli.postgres_pipeline import disposable_database


def benchmark(target, count=20000, rounds=5):
    if not 1000 <= count <= 200000 or not 1 <= rounds <= 20:
        raise ValueError("rows 1000..200000; rounds 1..20")
    with disposable_database(target) as url:
        upgrade(url)
        database = Database(url)
        try:
            with database.write("seed") as db:
                db.execute(
                    metadata.tables["tenants"]
                    .insert()
                    .values(id="t", name="synthetic", key_hash="unused")
                )
                db.execute(
                    metadata.tables["applications"]
                    .insert()
                    .values(id="a", tenant_id="t", slug="a", name="synthetic", description="")
                )
                db.execute(
                    metadata.tables["application_versions"]
                    .insert()
                    .values(id="v", application_id="a", version="1", notes="")
                )
                for start in range(0, count, 1000):
                    db.execute(
                        jobs.insert(),
                        [
                            dict(
                                id=f"{i:09d}",
                                tenant_id="t",
                                app_id="a",
                                version_id="v",
                                model="local" if i % 2 else "cloud",
                                status="failed" if i % 10 == 1 else "succeeded",
                                error="provider_timeout" if i % 10 == 1 else None,
                                attempts=1,
                                lease_until=0,
                                claim_token="",
                                created_at=i,
                                actor="benchmark",
                                request_id="synthetic",
                            )
                            for i in range(start, min(start + 1000, count))
                        ],
                    )
                db.execute(text("ANALYZE knowledge_index_jobs"))
            store = IndexJobs(database)
            captured = []

            def capture(conn, cursor, statement, parameters, context, executemany):
                if (
                    statement.startswith("SELECT")
                    and "LEFT OUTER JOIN" in statement
                    and "knowledge_index_jobs" in statement
                ):
                    captured.append((statement, parameters))

            event.listen(database.engine, "before_cursor_execute", capture)
            results = []
            for label, filters in [
                ("version", {}),
                ("model", {"model": "local"}),
                ("failure", {"model": "local", "status": "failed", "error": "provider_timeout"}),
            ]:
                matching = [
                    i
                    for i in range(count - 1, -1, -1)
                    if (not filters or i % 2) and (label != "failure" or i % 10 == 1)
                ]
                offset = len(matching) * 4 // 5
                anchor = matching[offset - 1]
                token = encode(
                    {"created_at": anchor, "id": f"{anchor:09d}"},
                    scope_key(
                        "t",
                        "a",
                        "v",
                        filters.get("model"),
                        filters.get("status"),
                        filters.get("error"),
                    ),
                )
                pages = []
                for mode, position in [
                    ("offset", {"offset": offset}),
                    ("cursor", {"cursor": token}),
                ]:
                    timings = []
                    store.list("t", "a", "v", **filters, **position)
                    for _ in range(rounds):
                        started = time.perf_counter()
                        page = store.list("t", "a", "v", **filters, **position)
                        timings.append((time.perf_counter() - started) * 1000)
                    statement, params = captured[-1]
                    with database.read() as db:
                        plan = db.exec_driver_sql(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params
                        ).scalar_one()
                    pages.append([row["id"] for row in page["data"]])
                    results.append(
                        dict(
                            case=label,
                            mode=mode,
                            offset=offset,
                            median_ms=statistics.median(timings),
                            samples_ms=timings,
                            plan=plan,
                        )
                    )
                assert pages[0] == pages[1] == [f"{i:09d}" for i in matching[offset : offset + 20]]
            with database.read() as db:
                version = db.execute(text("SELECT version()")).scalar_one()
            return dict(
                rows=count,
                rounds=rounds,
                server=version,
                results=results,
                same_rows=True,
                notes="Synthetic single version, empty checkpoints, warm cache, sequential queries; not API/network or concurrent-load latency.",
            )
        finally:
            database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = os.environ.get("NEXUS_TEST_POSTGRES_URL")
    if not target:
        parser.error("Set NEXUS_TEST_POSTGRES_URL to a test server with CREATE DATABASE permission")
    result = benchmark(target, args.rows, args.rounds)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("History benchmark passed; disposable database removed")


if __name__ == "__main__":
    main()
