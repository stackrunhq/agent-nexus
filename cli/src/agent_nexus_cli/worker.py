"""Durable knowledge ingestion worker; run independently from the API."""

import argparse
import asyncio
import os
import time

from agent_nexus.knowledge.jobs import run_once
from agent_nexus.knowledge.store import KnowledgeStore
from agent_nexus.storage.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit")
    parser.add_argument("--queue", choices=["documents", "indexes"], default="documents")
    args = parser.parse_args()
    database = None
    try:
        database = Database(
            os.getenv("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db")
        )
        store = KnowledgeStore(database)
        if args.queue == "indexes":
            asyncio.run(index_loop(database, args.once))
            return
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


async def index_loop(database, once):
    import httpx
    from agent_nexus.core.settings import Settings
    from agent_nexus.models.gateway import Gateway
    from agent_nexus.models.store import ModelStore
    from agent_nexus.knowledge.index_jobs import run_once as run_index

    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        gateway = Gateway(ModelStore(database), client, Settings.from_env().allowed_hosts)
        while True:
            worked = await run_index(database, gateway)
            if once:
                return
            if not worked:
                await asyncio.sleep(2)


if __name__ == "__main__":
    main()
