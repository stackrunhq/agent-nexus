"""Repeated multi-tenant index workers sharing one disposable PostgreSQL database."""

import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import time
from threading import Lock
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs, run_once
from agent_nexus.knowledge.index_checkpoints import checkpoints, batches
from agent_nexus.knowledge.jobs import run_once as parse_once
from agent_nexus.knowledge.pgvector_backend import setup
from agent_nexus.models.schemas import ModelConfig
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from agent_nexus_cli.postgres_pipeline import disposable_database


def benchmark(target, waves=10, workers=4, *, continuous=False):
    if not 1 <= waves <= 50 or workers not in (1, 2, 4):
        raise ValueError("waves 1..50, workers 1/2/4")
    upgrade(target)
    database = Database(target)
    try:
        setup(database)
    finally:
        database.close()

    async def model(request):
        await asyncio.sleep(0.005)
        return httpx.Response(
            200,
            json={"embeddings": [[1.0] + [0.0] * 63 for _ in json.loads(request.content)["input"]]},
        )

    with (
        patch.dict(
            os.environ,
            {
                "NEXUS_VECTOR_BACKEND": "pgvector",
                "NEXUS_INDEX_DAILY_LIMIT": "1000",
                "NEXUS_MODEL_DAILY_LIMIT": "10000",
            },
        ),
        TestClient(
            create_app(
                Settings("a" * 32, "b" * 32, target, {"localhost"}, "tenant"),
                httpx.MockTransport(model),
            )
        ) as client,
    ):
        admin = {"Authorization": "Bearer " + "a" * 32}

        def request(method, root, **kwargs):
            response = client.request(method, root, headers=admin, **kwargs)
            assert response.status_code in (200, 201, 202), response.status_code
            return response.json()

        client.app.state.gateway.store.put(
            ModelConfig(
                alias="embed",
                provider="ollama",
                model="mock",
                base_url="http://localhost",
                capabilities=["embeddings"],
                deployment="local",
            )
        )
        scopes = []
        names = {}
        for tenant_index in range(4):
            tenant = request(
                "POST", "/api/v1/admin/tenants", json={"name": f"tenant-{tenant_index}"}
            )
            names[tenant["id"]] = f"tenant-{tenant_index}"
            client.app.state.tenants.grant(tenant["id"], "embed", True)
            root = "/api/v1/admin/tenants/" + tenant["id"] + "/applications"
            app = request("POST", root, json={"name": "ERP", "slug": "erp"})
            root += "/" + app["id"] + "/versions"
            versions = (4 if tenant_index == 0 else 1) if continuous else 2
            for version_index in range(versions):
                version = request("POST", root, json={"version": str(version_index)})
                scope = root + "/" + version["id"]
                response = client.post(
                    scope + "/documents",
                    params={"filename": "manual.txt"},
                    content=("manual " * 2000)[:13750].encode(),
                    headers={**admin, "Content-Type": "application/octet-stream"},
                )
                assert response.status_code == 202
                assert parse_once(client.app.state.knowledge)
                request("PATCH", scope, json={"status": "published"})
                document = response.json()["id"]
                request("PATCH", scope + "/documents/" + document, json={"published": True})
                scopes.append((tenant["id"], scope, document))
        database = client.app.state.knowledge.database
        claims = []
        lock = Lock()
        original = IndexJobs.claim
        submitted = {}

        def claim(store):
            task = original(store)
            if task:
                with lock:
                    claims.append(
                        {
                            "id": task["id"],
                            "tenant": names[task["tenant_id"]],
                            "claimed_at": time.perf_counter(),
                        }
                    )
            return task

        async def drain():
            async def worker():
                while await run_once(database, client.app.state.gateway):
                    pass

            await asyncio.wait_for(asyncio.gather(*(worker() for _ in range(workers))), timeout=120)

        durations = []
        submission_requests = 0

        async def stream():
            done = asyncio.Event()

            async def producer():
                nonlocal submission_requests
                for tick in range(waves):
                    for tenant, scope, _ in scopes:
                        if names[tenant] != "tenant-0" and tick % 5:
                            continue
                        started = time.perf_counter()
                        task = await asyncio.to_thread(
                            request, "POST", scope + "/index-jobs", json={"model": "embed"}
                        )
                        submitted.setdefault(task["id"], started)
                        submission_requests += 1
                    await asyncio.sleep(0.02)
                done.set()

            async def worker():
                while True:
                    producer_finished = done.is_set()
                    worked = await run_once(database, client.app.state.gateway)
                    if not worked:
                        if producer_finished:
                            return
                        await asyncio.sleep(0.005)

            await asyncio.wait_for(
                asyncio.gather(producer(), *(worker() for _ in range(workers))), 120
            )

        with patch.object(IndexJobs, "claim", claim):
            if continuous:
                started = time.perf_counter()
                asyncio.run(stream())
                durations.append((time.perf_counter() - started) * 1000)
            for _ in range(0 if continuous else waves):
                for _, scope, _ in scopes:
                    started = time.perf_counter()
                    task = request("POST", scope + "/index-jobs", json={"model": "embed"})
                    submitted[task["id"]] = started
                    duplicate = request("POST", scope + "/index-jobs", json={"model": "embed"})
                    assert duplicate["id"] == task["id"]
                started = time.perf_counter()
                asyncio.run(drain())
                durations.append((time.perf_counter() - started) * 1000)
        with database.read() as db:
            rows = list(db.execute(jobs.select()).mappings())
            assert len(rows) == (len(submitted) if continuous else waves * len(scopes))
            assert all(row["status"] == "succeeded" and row["attempts"] == 1 for row in rows)
            assert db.execute(checkpoints.select()).first() is None
            assert db.execute(batches.select()).first() is None
        assert Counter(row["id"] for row in claims) == Counter(submitted.keys())
        for row in claims:
            row["wait_ms"] = (row["claimed_at"] - submitted[row["id"]]) * 1000
        counts = Counter(row["tenant"] for row in claims)
        assert set(counts) == set(names.values())
        if not continuous:
            assert set(counts.values()) == {waves * 2}
        for _, scope, document in scopes:
            result = request("GET", scope + "/vector-index?model=embed")
            assert result["status"] == "ready" and result["chunks"] == 16
            result = request(
                "POST", scope + "/vector-search", json={"model": "embed", "query": "manual"}
            )
            assert result["method"] == "pgvector_cosine"
            assert all(row["document_id"] == document for row in result["data"])
        return {
            "waves": waves,
            "workers": workers,
            "tenants": 4,
            "versions_per_tenant": [4, 1, 1, 1] if continuous else [2, 2, 2, 2],
            "continuous": continuous,
            "submission_requests": submission_requests if continuous else waves * len(scopes) * 2,
            "successful_jobs": len(rows),
            "claimed_per_tenant": dict(counts),
            "wave_drain_ms": durations,
            "tenant_max_wait_ms": {
                name: max(row["wait_ms"] for row in claims if row["tenant"] == name)
                for name in names.values()
            },
            "duplicate_claims": 0,
            "remaining_checkpoints": 0,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--waves", type=int, default=10, choices=range(1, 51))
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Uneven producer remains active while workers consume",
    )
    args = parser.parse_args()
    target = os.getenv("NEXUS_TEST_PGVECTOR_URL")
    if not target:
        parser.error(
            "Set NEXUS_TEST_PGVECTOR_URL to a dedicated test server with CREATE DATABASE permission"
        )
    results = []
    for workers in (1, 4):
        with disposable_database(target) as database:
            results.append(benchmark(database, args.waves, workers, continuous=args.continuous))
    args.output.write_text(
        json.dumps(
            {
                "scope": "one PostgreSQL database per worker-count scenario; concurrent async workers and threaded database calls",
                "model": "mock 64 dimensions, 5ms async delay; not real model performance",
                "fairness_scope": "finite measured arrival schedule; no starvation observed is not a scheduling guarantee",
                "arrival_schedule": "hot tenant each tick; three cold tenants every fifth tick; 20ms sleep after submissions"
                if args.continuous
                else "balanced waves drained before next submission",
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
