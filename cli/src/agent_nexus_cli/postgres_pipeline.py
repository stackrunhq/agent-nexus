"""Full synthetic pipeline in disposable PostgreSQL databases; sampled client RSS."""

import argparse
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import platform
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from agent_nexus_cli.pipeline_benchmark import scenario


def rss_bytes():
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak",
                    "working",
                    "quota_peak_paged",
                    "quota_paged",
                    "quota_peak_nonpaged",
                    "quota_nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        data = Counters()
        data.cb = ctypes.sizeof(data)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb):
            raise OSError(ctypes.get_last_error(), "Cannot sample process working set")
        return data.working
    if platform.system() == "Linux":
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    raise RuntimeError("RSS sampler supports Windows and Linux")


@contextmanager
def disposable_database(target):
    url = make_url(target)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL test server required")
    name = "nexus_pipeline_" + uuid4().hex
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    created = False
    try:
        with engine.connect() as db:
            db.execute(text("CREATE DATABASE " + name))
        created = True
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        try:
            if created:
                with engine.connect() as db:
                    db.execute(text("DROP DATABASE " + name + " WITH (FORCE)"))
        finally:
            engine.dispose()


def measured(target, count, rounds):
    stop = Event()
    samples = [rss_bytes()]
    errors = []

    def sample():
        try:
            while not stop.wait(0.02):
                samples.append(rss_bytes())
        except Exception as exc:
            errors.append(type(exc).__name__)

    thread = Thread(target=sample, daemon=True)
    thread.start()
    try:
        result = scenario(count, rounds=rounds, postgres_target=target)
    finally:
        stop.set()
        thread.join()
    if errors:
        raise RuntimeError("RSS sampling failed")
    return {
        **result,
        "client_rss_baseline_bytes": samples[0],
        "client_rss_sampled_peak_bytes": max(samples),
        "rss_sample_count": len(samples),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=range(1, 21), default=5)
    args = parser.parse_args()
    target = os.getenv("NEXUS_TEST_PGVECTOR_URL")
    if not target:
        parser.error("Set NEXUS_TEST_PGVECTOR_URL to a test server with CREATE DATABASE permission")
    results = []
    for count in (16, 64, 128, 129):
        with disposable_database(target) as database:
            results.append(measured(database, count, args.rounds))
    args.output.write_text(
        json.dumps(
            {
                "backend": "postgresql_pgvector",
                "platform": platform.platform(),
                "python": platform.python_version(),
                "models": "deterministic_http_mock",
                "memory_scope": "20ms samples of Python client RSS/working set; excludes parser subprocess and PostgreSQL; not exact peak",
                "load_scope": "sequential pipeline scenarios; four concurrent API requests compete for one remaining model call",
                "scenarios": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
