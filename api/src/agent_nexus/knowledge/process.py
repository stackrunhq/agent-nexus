"""Disposable parser subprocess: no database handles or provider credentials."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys


def main():
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024,) * 2)
    from .parsing import MAX_FILE_BYTES, DocumentError, parse_document
    from .chunking import chunk_document

    try:
        with Path(sys.argv[1]).open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        parsed = parse_document(sys.argv[3], content)
        result = {
            "warnings": parsed.warnings,
            "chunks": [asdict(c) for c in chunk_document(parsed)],
        }
    except DocumentError as exc:
        result = {"error": exc.code}
    except MemoryError:
        result = {"error": "parser_resource_limit"}
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")


if __name__ == "__main__":
    main()
