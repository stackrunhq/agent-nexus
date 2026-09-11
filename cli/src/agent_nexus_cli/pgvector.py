"""Provision the optional pgvector derived cache using a database owner identity."""

import os
from agent_nexus.storage.database import Database
from agent_nexus.knowledge.pgvector_backend import setup


def main():
    database = Database(
        os.environ.get("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db")
    )
    try:
        setup(database)
        print("pgvector cache ready; enable the backend and rebuild version/model indexes.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
