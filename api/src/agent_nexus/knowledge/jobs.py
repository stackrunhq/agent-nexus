"""Run each document in a disposable process with a bounded lifetime."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PARSER_TIMEOUT = 60
MAX_RESULT_BYTES = 32 * 1024 * 1024


def parse_isolated(filename, content):
    with tempfile.TemporaryDirectory(prefix="nexus-parse-") as folder:
        source, target = Path(folder) / "input", Path(folder) / "result.json"
        source.write_bytes(content)
        # Keep only OS/Python startup essentials. The child never receives Nexus secrets.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG"}
        }
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "agent_nexus.knowledge.process",
                    str(source),
                    str(target),
                    filename,
                ],
                env=environment,
                cwd=folder,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PARSER_TIMEOUT,
            )
            if process.returncode != 0 or not target.is_file():
                return {"error": "parser_process_failed"}
            with target.open("rb") as stream:
                raw = stream.read(MAX_RESULT_BYTES + 1)
            if len(raw) > MAX_RESULT_BYTES:
                return {"error": "parser_result_too_large"}
            return json.loads(raw)
        except subprocess.TimeoutExpired:
            return {"error": "parser_timeout"}
        except (OSError, ValueError):
            return {"error": "parser_process_failed"}


def run_once(store):
    task = store.claim()
    if task is None:
        return False
    result = parse_isolated(task["filename"], bytes(task["content"]))
    store.finish(task["id"], task["claim_token"], result=result, error=result.get("error"))
    return True
