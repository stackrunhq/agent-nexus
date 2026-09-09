"""Preview local document parsing as JSON; does not import into the knowledge base."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

from agent_nexus.knowledge.chunking import chunk_document
from agent_nexus.knowledge.parsing import MAX_FILE_BYTES, DocumentError, parse_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--overlap", type=int, default=150)
    args = parser.parse_args()
    try:
        with args.file.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        document = parse_document(args.file.name, content)
        chunks = chunk_document(document, args.chunk_size, args.overlap)
        print(json.dumps({"filename": args.file.name,
                          "sha256": hashlib.sha256(content).hexdigest(),
                          "warnings": document.warnings,
                          "chunks": [asdict(chunk) for chunk in chunks]}, ensure_ascii=True))
    except (OSError, DocumentError, ValueError) as exc:
        code = exc.code if isinstance(exc, DocumentError) else "invalid_input"
        print(json.dumps({"error": code}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
