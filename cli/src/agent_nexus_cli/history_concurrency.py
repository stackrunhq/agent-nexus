"""Multi-tenant history reads with synthetic active checkpoint metadata."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
from threading import Barrier
import time

from sqlalchemy import event, text
from agent_nexus.storage.database import Database, metadata
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from agent_nexus_cli.database import upgrade
from agent_nexus_cli.postgres_pipeline import disposable_database


def benchmark(target, rows=2000, rounds=10):
    if not 100 <= rows <= 20000 or not 1 <= rounds <= 100:
        raise ValueError("rows 100..20000 per tenant; rounds 1..100")
    with disposable_database(target) as url:
        upgrade(url)
        database = Database(url)
        try:
            with database.write("seed") as db:
                for tenant in range(4):
                    key = str(tenant)
                    db.execute(
                        metadata.tables["tenants"]
                        .insert()
                        .values(id=key, name="synthetic", key_hash="unused-" + key)
                    )
                    db.execute(
                        metadata.tables["applications"]
                        .insert()
                        .values(id=key, tenant_id=key, slug="app", name="synthetic", description="")
                    )
                    db.execute(
                        metadata.tables["application_versions"]
                        .insert()
                        .values(id=key, application_id=key, version="1", notes="")
                    )
                    for start in range(0, rows, 500):
                        chunk = range(start, min(start + 500, rows))
                        db.execute(
                            jobs.insert(),
                            [
                                dict(
                                    id=f"{key}:{i:09d}",
                                    tenant_id=key,
                                    app_id=key,
                                    version_id=key,
                                    model="local",
                                    status="processing" if i % 4 == 0 else "succeeded",
                                    error=None,
                                    attempts=1,
                                    lease_until=2000000000,
                                    claim_token="synthetic",
                                    created_at=i,
                                    actor="benchmark",
                                    request_id="synthetic",
                                )
                                for i in chunk
                            ],
                        )
                        active = [f"{key}:{i:09d}" for i in chunk if i % 4 == 0]
                        db.execute(
                            metadata.tables["knowledge_index_checkpoints"].insert(),
                            [
                                dict(
                                    job_id=job,
                                    content_revision="synthetic",
                                    model_revision="synthetic",
                                    dimensions=2,
                                    payload="[]",
                                )
                                for job in active
                            ],
                        )
                        db.execute(
                            metadata.tables["knowledge_index_batches"].insert(),
                            [
                                dict(job_id=job, start=batch * 16, payload="[]")
                                for job in active
                                for batch in range(8)
                            ],
                        )
                for name in [
                    "knowledge_index_jobs",
                    "knowledge_index_checkpoints",
                    "knowledge_index_batches",
                ]:
                    db.execute(text("ANALYZE " + name))
            store = IndexJobs(database)
            captured = []

            def capture(conn, cursor, statement, parameters, context, executemany):
                if statement.startswith("SELECT") and "knowledge_index_batches" in statement:
                    captured.append((statement, parameters))

            event.listen(database.engine, "before_cursor_execute", capture)
            store.list("0", "0", "0", model="local")
            statement, params = captured[-1]
            event.remove(database.engine, "before_cursor_execute", capture)
            with database.read() as db:
                plan = db.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params
                ).scalar_one()
                server = db.execute(text("SELECT version()")).scalar_one()
            results = []
            for workers in (1, 4):
                barrier = Barrier(workers)

                def read(worker, barrier=barrier):
                    barrier.wait(timeout=30)
                    samples = []
                    for step in range(rounds):
                        key = str((worker + step) % 4)
                        started = time.perf_counter()
                        page = store.list(key, key, key, model="local")
                        samples.append((time.perf_counter() - started) * 1000)
                        assert [row["id"] for row in page["data"]] == [
                            f"{key}:{i:09d}" for i in range(rows - 1, rows - 21, -1)
                        ]
                        assert all(
                            row["saved_batches"]
                            == (8 if int(row["id"].split(":")[1]) % 4 == 0 else 0)
                            for row in page["data"]
                        )
                    return samples

                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    samples = [
                        sample for group in pool.map(read, range(workers)) for sample in group
                    ]
                results.append(
                    dict(
                        workers=workers,
                        queries=len(samples),
                        wall_ms=(time.perf_counter() - started) * 1000,
                        median_ms=statistics.median(samples),
                        max_ms=max(samples),
                        samples_ms=samples,
                    )
                )
            return dict(
                server=server,
                tenants=4,
                rows_per_tenant=rows,
                active_per_tenant=len(range(0, rows, 4)),
                batches_per_active=8,
                rounds=rounds,
                results=results,
                plan=plan,
                checks="All page IDs tenant-scoped; all saved batch counts exact",
                notes="Synthetic metadata only, no model/Worker writes; warm cache; sequential 1 then 4 threads; not HTTP latency or capacity SLA",
            )
        finally:
            database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = os.environ.get("NEXUS_TEST_POSTGRES_URL")
    if not target:
        parser.error("Set NEXUS_TEST_POSTGRES_URL to a disposable test server")
    result = benchmark(target, args.rows, args.rounds)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Concurrent history checks passed; disposable database removed")


if __name__ == "__main__":
    main()
