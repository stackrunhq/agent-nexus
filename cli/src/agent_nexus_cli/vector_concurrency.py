"""Bounded native pgvector concurrency benchmark; Python allocations, not server RSS."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
from threading import Barrier
import time
import tracemalloc

from agent_nexus.storage.database import Database
from agent_nexus_cli.vector_benchmark import benchmark


def measure(database, workers, count, rounds=10):
    if workers not in (1, 2, 4) or count not in (128, 1024) or not 1 <= rounds <= 100:
        raise ValueError("workers 1/2/4, count 128/1024, rounds 1..100")
    if database.sqlite:
        raise ValueError("Requires an initialized dedicated PostgreSQL database")
    if tracemalloc.is_tracing():
        raise RuntimeError("Run benchmark in a process without an active allocation tracer")
    barrier = Barrier(workers)

    def run(index):
        barrier.wait(timeout=30)
        return benchmark(database, count=count, dimensions=64, rounds=rounds, seed=42 + index)

    tracemalloc.start()
    try:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, range(workers)))
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if any(row["mean_top_k_overlap"] != 1 or row["max_score_error"] > 1e-5 for row in results):
        raise RuntimeError("Concurrent native retrieval failed reference comparison")
    return {
        "workers": workers,
        "count_per_worker": count,
        "rounds_per_worker": rounds,
        "elapsed_seconds_including_build_reference_and_cleanup": elapsed,
        "python_traced_peak_bytes": peak,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=10, choices=range(1, 101))
    args = parser.parse_args()
    target = os.getenv("NEXUS_TEST_PGVECTOR_URL")
    if not target:
        parser.error("Set NEXUS_TEST_PGVECTOR_URL to a dedicated initialized test database")
    database = Database(target, prepare=False)
    try:
        report = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "scope": "native cache only; no API, model, document parser or recovery",
            "memory_scope": "tracemalloc Python allocations across all threads; excludes PostgreSQL and most native allocations",
            "timing_scope": "tracing enabled; includes client connection overhead; not comparable to uninstrumented latency",
            "scenarios": [
                measure(database, workers, count, args.rounds)
                for count in (128, 1024)
                for workers in (1, 2, 4)
            ],
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    finally:
        database.close()


if __name__ == "__main__":
    main()
