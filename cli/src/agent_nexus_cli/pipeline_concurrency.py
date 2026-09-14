"""Concurrent isolated pipeline processes with local process-tree RSS sampling."""

import argparse
from contextlib import ExitStack, suppress
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from agent_nexus_cli.pipeline_benchmark import scenario
from agent_nexus_cli.postgres_pipeline import disposable_database, rss_bytes
from agent_nexus_cli.process_tree import parents, descendants


def run(target, postgres_pid, workers):
    peaks = {"pipelines": 0, "parser_descendants": 0, "postgres_tree": 0}
    missing = 0
    samples = 0
    observed_parsers = set()
    processes = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="nexus-concurrent-") as directory, ExitStack() as stack:
        outputs = []
        try:
            for index in range(workers):
                database = stack.enter_context(disposable_database(target))
                output = Path(directory) / f"worker-{index}.json"
                outputs.append(output)
                env = {**os.environ, "NEXUS_TEST_PGVECTOR_URL": database}
                log = stack.enter_context((Path(directory) / f"worker-{index}.log").open("w"))
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "agent_nexus_cli.pipeline_concurrency",
                            "--child",
                            "--output",
                            str(output),
                        ],
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                )
            while any(process.poll() is None for process in processes):
                if time.perf_counter() - started > 180:
                    raise TimeoutError("Concurrent pipelines exceeded 180 seconds")
                mapping = parents()
                roots = {process.pid for process in processes if process.poll() is None}
                actual = set()
                for output in outputs:
                    pid_file = output.with_suffix(".pid")
                    if pid_file.exists():
                        with suppress(ValueError):
                            pid = int(pid_file.read_text())
                            if pid in mapping:
                                actual.add(pid)
                parsers = descendants(mapping, actual) - actual
                observed_parsers.update(parsers)
                for group, pids in {
                    "pipelines": roots | actual,
                    "parser_descendants": parsers,
                    "postgres_tree": descendants(mapping, {postgres_pid}),
                }.items():
                    total = 0
                    for pid in pids:
                        try:
                            total += rss_bytes(pid)
                        except OSError:
                            missing += 1
                    peaks[group] = max(peaks[group], total)
                samples += 1
                time.sleep(0.02)
            if any(process.returncode != 0 for process in processes):
                raise RuntimeError("A concurrent pipeline failed; no successful report written")
            results = [json.loads(output.read_text()) for output in outputs]
            if not observed_parsers or peaks["postgres_tree"] == 0:
                raise RuntimeError("Required process groups were not observed")
            return {
                "workers": workers,
                "wall_seconds": time.perf_counter() - started,
                "sampled_peak_sum_rss_bytes": peaks,
                "samples": samples,
                "unreadable_or_exited_process_samples": missing,
                "observed_parser_processes": len(observed_parsers),
                "results": results,
            }
        finally:
            live_roots = {process.pid for process in processes if process.poll() is None}
            if live_roots:
                for pid in descendants(parents(), live_roots) - live_roots:
                    with suppress(ProcessLookupError, PermissionError):
                        os.kill(pid, signal.SIGTERM)
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--postgres-pid", type=int)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    target = os.getenv("NEXUS_TEST_PGVECTOR_URL")
    if not target:
        parser.error("Set NEXUS_TEST_PGVECTOR_URL to a local dedicated test server")
    if args.child:
        args.output.with_suffix(".pid").write_text(str(os.getpid()))
        args.output.write_text(
            json.dumps(scenario(128, rounds=3, postgres_target=target)), encoding="utf-8"
        )
        return
    if not args.postgres_pid or args.postgres_pid <= 0:
        parser.error("Provide the local dedicated PostgreSQL postmaster PID")
    rss_bytes(args.postgres_pid)
    report = {
        "scope": "2/4 successful isolated 128-chunk pipelines, mocked models; separate databases",
        "memory_scope": "sampled sum of working sets/RSS per process group, shared pages double counted; not physical unique memory",
        "sampling": "20ms sleep plus enumeration cost; exits may be missed; group peaks are not simultaneous",
        "scenarios": [run(target, args.postgres_pid, workers) for workers in (2, 4)],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
