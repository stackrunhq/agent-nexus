"""Repeatable native exact-search benchmark; no model calls or real manual content."""

import argparse
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
from uuid import uuid4

from sqlalchemy import text
from agent_nexus.storage.database import Database
from agent_nexus.knowledge import pgvector_backend as backend


def normalized(values):
    norm = math.hypot(*values)
    return [value / norm for value in values]


def benchmark(database, count=128, dimensions=64, rounds=10, seed=42):
    rng = random.Random(seed)
    vectors = [normalized([rng.uniform(-1, 1) for _ in range(dimensions)]) for _ in range(count)]
    payload = json.dumps(vectors)
    version = str(uuid4())
    timings, overlaps, errors = [], [], []
    k = min(count, 10)
    with database.read() as db:
        backend.require(db)
        pg_version = db.execute(text("SHOW server_version")).scalar_one()
        vector_version = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar_one()
    try:
        started = time.perf_counter()
        with database.write("benchmark:" + version) as db:
            backend.save(db, version, "benchmark", payload)
        build_seconds = time.perf_counter() - started
        for _ in range(rounds):
            query = normalized([rng.uniform(-1, 1) for _ in range(dimensions)])
            expected = sorted(
                [
                    (i, sum(a * b for a, b in zip(query, vector, strict=True)))
                    for i, vector in enumerate(vectors)
                ],
                key=lambda item: (-item[1], item[0]),
            )[:k]
            started = time.perf_counter()
            actual = backend.rank(database, version, "benchmark", payload, query, k)
            timings.append((time.perf_counter() - started) * 1000)
            overlaps.append(len({i for i, _ in expected} & {row["ordinal"] for row in actual}) / k)
            for row in actual:
                expected_score = sum(
                    a * b for a, b in zip(query, vectors[row["ordinal"]], strict=True)
                )
                errors.append(abs(row["score"] - expected_score))
        return {
            "postgres_version": pg_version,
            "pgvector_version": vector_version,
            "count": count,
            "dimensions": dimensions,
            "rounds": rounds,
            "seed": seed,
            "top_k": k,
            "mean_top_k_overlap": statistics.mean(overlaps),
            "max_score_error": max(errors),
            "build_seconds": build_seconds,
            "median_query_ms": statistics.median(timings),
            "p95_query_ms": sorted(timings)[math.ceil(len(timings) * 0.95) - 1],
            "scope": "Synthetic native cache only; not end-to-end capacity or model quality.",
        }
    finally:
        with database.write("benchmark:" + version) as db:
            db.execute(
                text("DELETE FROM nexus_vectors.entries WHERE version_id=:version"),
                {"version": version},
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=128)
    parser.add_argument("--dimensions", type=int, default=64)
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    target = os.environ.get("NEXUS_TEST_PGVECTOR_URL")
    if not target:
        parser.error("Set NEXUS_TEST_PGVECTOR_URL to a dedicated initialized test database")
    if not (1 <= args.count <= 4096 and 1 <= args.dimensions <= 4096 and 1 <= args.rounds <= 100):
        parser.error("count 1..4096, dimensions 1..4096, rounds 1..100")
    if args.count * args.dimensions > 1048576:
        parser.error("Benchmark is bounded to 1048576 scalar values")
    database = Database(target, prepare=False)
    try:
        result = benchmark(database, args.count, args.dimensions, args.rounds)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("Benchmark complete; report:", args.output)
    finally:
        database.close()


if __name__ == "__main__":
    main()
