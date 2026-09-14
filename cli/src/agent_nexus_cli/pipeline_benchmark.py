"""Offline API/Worker pipeline benchmark in a disposable SQLite database; mocked models."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import math
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app
from agent_nexus.knowledge.index_checkpoints import IndexCheckpoint
from agent_nexus.knowledge.index_jobs import jobs, run_once as index_once
from agent_nexus.knowledge.jobs import run_once as parse_once
from agent_nexus.knowledge.search import readable_chunks
from agent_nexus.models.schemas import ModelConfig
from agent_nexus_cli.database import upgrade


def scenario(count, dimensions=64, rounds=5, *, postgres_target=None):
    if count not in (16, 64, 128, 129) or not 2 <= dimensions <= 4096 or not 1 <= rounds <= 20:
        raise ValueError("Use counts 16/64/128/129, dimensions 2..4096, rounds 1..20")
    calls = []

    def model(request):
        body = json.loads(request.content)
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "message": {
                        "content": json.dumps(
                            {"answer": "Password settings [1]", "citations": ["1"]}
                        )
                    },
                },
            )
        calls.append(len(body["input"]))
        vectors = []
        for text in body["input"]:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([(digest[i % 32] + 1) / 256 for i in range(dimensions)])
        return httpx.Response(200, json={"embeddings": vectors})

    timings = {}

    def timed(name, operation):
        start = time.perf_counter()
        try:
            return operation()
        finally:
            timings[name] = (time.perf_counter() - start) * 1000

    with (
        tempfile.TemporaryDirectory(prefix="nexus-pipeline-") as directory,
        patch.dict(
            os.environ,
            {
                "NEXUS_VECTOR_BACKEND": "pgvector" if postgres_target else "portable",
                "NEXUS_MODEL_DAILY_LIMIT": "1000",
                "NEXUS_INDEX_DAILY_LIMIT": "100",
            },
        ),
    ):
        path = postgres_target or str(Path(directory) / "benchmark.db")
        upgrade(path)
        if postgres_target:
            from agent_nexus.storage.database import Database
            from agent_nexus.knowledge.pgvector_backend import setup

            database = Database(path)
            try:
                setup(database)
            finally:
                database.close()
        with TestClient(
            create_app(
                Settings("a" * 32, "b" * 32, path, {"localhost"}, "tenant"),
                httpx.MockTransport(model),
            )
        ) as client:
            admin = {"Authorization": "Bearer " + "a" * 32}

            def request(method, path, expected=None, **kwargs):
                response = client.request(method, path, headers=admin, **kwargs)
                if response.status_code not in ((200, 201) if expected is None else (expected,)):
                    raise RuntimeError(f"Unexpected benchmark response: {response.status_code}")
                return response.json()

            tenant = request("POST", "/api/v1/admin/tenants", json={"name": "benchmark"})
            tenant_root = "/api/v1/admin/tenants/" + tenant["id"]
            app = request(
                "POST", tenant_root + "/applications", json={"name": "ERP", "slug": "erp"}
            )
            root = tenant_root + "/applications/" + app["id"] + "/versions"
            version = request("POST", root, json={"version": "1"})
            root += "/" + version["id"]
            length = 1000 + (count - 1) * 850
            content = ("password settings manual " * (length // 25 + 2))[:length].encode()

            def upload():
                response = client.post(
                    root + "/documents",
                    params={"filename": "manual.txt"},
                    content=content,
                    headers={**admin, "Content-Type": "application/octet-stream"},
                )
                assert response.status_code == 202
                return response.json()

            document = timed("upload_ms", upload)
            store = client.app.state.knowledge
            assert timed("parse_worker_ms", lambda: parse_once(store))
            parsed = request("GET", root + "/documents/" + document["id"])
            assert parsed["status"] == "ready"
            request("PATCH", root, json={"status": "published"})
            request("PATCH", root + "/documents/" + document["id"], json={"published": True})
            actual = len(readable_chunks(store.database, tenant["id"], app["id"], version["id"]))
            assert actual == count
            for alias, capability in (("embed", "embeddings"), ("chat", "chat")):
                client.app.state.gateway.store.put(
                    ModelConfig(
                        alias=alias,
                        provider="ollama",
                        model="synthetic",
                        base_url="http://localhost",
                        deployment="local",
                        capabilities=[capability],
                    )
                )
                client.app.state.tenants.grant(tenant["id"], alias, True)
            report = {
                "chunks": actual,
                "characters": len(content),
                "dimensions": dimensions,
                "rounds": rounds,
                "timings": timings,
            }
            if count > 128:
                result = request("POST", root + "/index-jobs", 409, json={"model": "embed"})
                assert result["error"]["code"] == "index_capacity" and not calls
                return {**report, "capacity_rejected_before_model": True}
            request("POST", root + "/index-jobs", 202, json={"model": "embed"})
            assert timed(
                "build_worker_ms",
                lambda: asyncio.run(index_once(store.database, client.app.state.gateway)),
            )
            assert request("GET", root + "/vector-index?model=embed")["status"] == "ready"
            assert sum(calls) == count
            report["initial_embedding_calls"] = len(calls)
            calls.clear()
            task = request("POST", root + "/index-jobs", 202, json={"model": "embed"})
            save = IndexCheckpoint.save

            def interrupt(checkpoint, *args, **kwargs):
                save(checkpoint, *args, **kwargs)
                raise asyncio.CancelledError()

            with patch.object(IndexCheckpoint, "save", interrupt):
                try:
                    timed(
                        "interrupted_attempt_ms",
                        lambda: asyncio.run(index_once(store.database, client.app.state.gateway)),
                    )
                except asyncio.CancelledError:
                    pass
                else:
                    raise AssertionError("Expected interrupted worker")
            assert calls == [16]
            with store.database.write("benchmark") as db:
                db.execute(jobs.update().where(jobs.c.id == task["id"]).values(lease_until=0))
            calls.clear()
            timed(
                "resume_worker_ms",
                lambda: asyncio.run(index_once(store.database, client.app.state.gateway)),
            )
            assert sum(calls) == count - 16
            report["resumed_embedding_calls"] = len(calls)
            report["reused_chunks"] = 16
            restored = next(
                row
                for row in request("GET", root + "/index-jobs")["data"]
                if row["id"] == task["id"]
            )
            assert restored["status"] == "succeeded" and restored["attempts"] == 2
            assert restored["saved_batches"] == 0
            assert request("GET", root + "/vector-index?model=embed")["status"] == "ready"
            for endpoint in ("search", "vector-search", "hybrid-search", "answers"):
                samples = []
                for _ in range(rounds):
                    body = {"query": "password"}
                    if endpoint != "search":
                        body["model"] = "embed"
                    if endpoint == "answers":
                        body["chat_model"] = "chat"
                    start = time.perf_counter()
                    result = request("POST", root + "/" + endpoint, json=body)
                    samples.append((time.perf_counter() - start) * 1000)
                    sources = result["citations"] if endpoint == "answers" else result["data"]
                    assert sources and sources[0]["document_id"] == document["id"]
                timings[endpoint] = {
                    "samples_ms": samples,
                    "median_ms": statistics.median(samples),
                    "p95_ms": sorted(samples)[math.ceil(len(samples) * 0.95) - 1],
                }
            used = request("GET", tenant_root + "/model-usage")["daily_used"]
            request("PUT", tenant_root + "/model-quota", json={"daily_limit": used + 1})
            before = len(calls)

            def concurrent_query(_):
                return client.post(
                    root + "/vector-search",
                    headers=admin,
                    json={"model": "embed", "query": "password"},
                ).status_code

            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(concurrent_query, range(4)))
            assert sorted(statuses) == [200, 429, 429, 429] and len(calls) == before + 1
            report["concurrent_quota_statuses"] = sorted(statuses)
            request("PUT", tenant_root + "/index-quota", json={"daily_limit": 0})
            request("POST", root + "/index-jobs", 429, json={"model": "embed"})
            request("PUT", tenant_root + "/model-quota", json={"daily_limit": 0})
            before = len(calls)
            request(
                "POST", root + "/vector-search", 429, json={"model": "embed", "query": "password"}
            )
            assert len(calls) == before
            report["quota_blocks_before_model"] = True
            return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=5, choices=range(1, 21))
    args = parser.parse_args()
    report = {
        "backend": "sqlite_portable",
        "models": "deterministic_http_mock",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "limitations": [
            "single process TestClient; no network latency or real model quality",
            "simulated cancellation; lease wait excluded; no concurrent load",
            "synthetic TXT only; not PostgreSQL, Docker or scanned PDF capacity",
        ],
        "scenarios": [scenario(count, rounds=args.rounds) for count in (16, 64, 128, 129)],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
