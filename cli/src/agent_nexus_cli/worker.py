"""Durable knowledge ingestion worker; run independently from the API."""

import argparse
import os
import time

from agent_nexus.knowledge.jobs import run_once
from agent_nexus.knowledge.store import KnowledgeStore
from agent_nexus.storage.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit")
    args = parser.parse_args()
    database = None
    try:
        database = Database(
            os.getenv("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db")
        )
        store = KnowledgeStore(database)
        while True:
            worked = run_once(store)
            if args.once:
                return
            if not worked:
                time.sleep(2)
    except KeyboardInterrupt:
        return
    except Exception:
        parser.exit(
            1,
            "Worker stopped; check database readiness and connectivity. Task leases permit recovery.\n",
        )
    finally:
        if database:
            database.close()


if __name__ == "__main__":
    main()
