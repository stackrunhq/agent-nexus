"""Coordinated reads during real checkpoint saves and transactional completion."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import statistics
import time
from sqlalchemy import select, func

from agent_nexus.knowledge.index_checkpoints import IndexCheckpoint, clear, batches, checkpoints
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs


def mixed(database, rows, rounds):
    store = IndexJobs(database)
    with database.write("index-queue") as db:
        identifiers = [f"{key}:{rows - 1:09d}" for key in range(4)]
        clear(db, identifiers)
        db.execute(
            jobs.update()
            .where(jobs.c.id.in_(identifiers))
            .values(status="succeeded", claim_token="", lease_until=0)
        )
    barrier = Barrier(5, timeout=30)
    writes = []

    def writer():
        for cycle in range(rounds):
            key = str(cycle % 4)
            identifier = f"{key}:{rows - 1:09d}"
            task = {"id": identifier, "claim_token": f"mixed-{cycle}"}
            checkpoint = IndexCheckpoint(database, task)
            for phase in range(4):
                barrier.wait()
                started = time.perf_counter()
                if phase == 0:
                    with database.write("index-queue") as db:
                        clear(db, [identifier])
                        db.execute(
                            jobs.update()
                            .where(jobs.c.id == identifier)
                            .values(
                                status="processing",
                                error=None,
                                claim_token=task["claim_token"],
                                lease_until=int(time.time()) + 300,
                            )
                        )
                elif phase in (1, 2):
                    checkpoint.save("synthetic", "synthetic", [[1.0, 0.0]], 2, start=phase - 1)
                else:
                    with database.write("index-queue") as db:
                        store.finish(db, task, "synthetic_failure" if cycle % 2 else None)
                writes.append((time.perf_counter() - started) * 1000)
                barrier.wait()
                barrier.wait()

    def reader(worker):
        samples = []
        observations = 0
        for cycle in range(rounds):
            key = str(cycle % 4)
            for phase in range(4):
                barrier.wait()
                started = time.perf_counter()
                page = store.list(key, key, key, model="local")
                samples.append((time.perf_counter() - started) * 1000)
                assert [row["id"] for row in page["data"]] == [
                    f"{key}:{i:09d}" for i in range(rows - 1, rows - 21, -1)
                ]
                row = page["data"][0]
                assert (row["status"] == "processing" and 0 <= row["saved_batches"] <= 2) or (
                    row["status"] in ("succeeded", "failed") and row["saved_batches"] == 0
                )
                barrier.wait()
                committed = store.list(key, key, key, model="local")["data"][0]
                assert committed["saved_batches"] == (phase if phase < 3 else 0)
                assert committed["status"] == (
                    "processing" if phase < 3 else "failed" if cycle % 2 else "succeeded"
                )
                # Also read a different tenant during each phase.
                other = str((cycle + worker + 1) % 4)
                assert all(
                    row["id"].startswith(other + ":")
                    for row in store.list(other, other, other)["data"]
                )
                observations += 3
                barrier.wait()
        return samples, observations

    def guarded(operation, *args):
        try:
            return operation(*args)
        except BaseException:
            barrier.abort()
            raise

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=5) as pool:
        write = pool.submit(guarded, writer)
        readers = [pool.submit(guarded, reader, i) for i in range(4)]
        data = [future.result() for future in readers]
        write.result()
    with database.read() as db:
        for table in (batches, checkpoints):
            assert (
                db.execute(
                    select(func.count()).select_from(table).where(table.c.job_id.in_(identifiers))
                ).scalar_one()
                == 0
            )
    samples = [sample for group, _ in data for sample in group]
    return dict(
        pool_size=2,
        max_overflow=0,
        pool_timeout_seconds=5,
        final_mutated_checkpoints=0,
        rounds=rounds,
        readers=4,
        writers=1,
        reads=sum(count for _, count in data),
        writes=len(writes),
        wall_ms=(time.perf_counter() - started) * 1000,
        read_median_ms=statistics.median(samples),
        read_max_ms=max(samples),
        write_median_ms=statistics.median(writes),
        read_samples_ms=samples,
        write_samples_ms=writes,
        checks="Overlapping reads show valid status/count pairs; post-commit counts exact; other tenant IDs isolated",
        notes="Barrier-coordinated synthetic lifecycle; no model calls; query samples time only racing read, counts include post-commit and other-tenant reads",
    )
