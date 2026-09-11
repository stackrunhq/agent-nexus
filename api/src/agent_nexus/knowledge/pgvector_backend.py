"""Optional native vector cache derived from portable canonical snapshots."""

import hashlib
import json
import os
from sqlalchemy import text
from agent_nexus.core.errors import GatewayError


def enabled(database):
    mode = os.getenv("NEXUS_VECTOR_BACKEND", "portable")
    if mode not in {"portable", "pgvector"}:
        raise RuntimeError("NEXUS_VECTOR_BACKEND must be portable or pgvector")
    if mode == "pgvector" and database.sqlite:
        raise GatewayError(503, "vector_backend_unavailable", "pgvector requires PostgreSQL")
    return mode == "pgvector"


def signature(payload):
    return hashlib.sha256(payload.encode()).hexdigest()


def check(database):
    with database.read() as db:
        require(db)


def require(db):
    if not db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector' AND n.nspname='public') AND to_regclass('nexus_vectors.entries') IS NOT NULL"
        )
    ).scalar_one():
        raise GatewayError(
            503, "vector_backend_unavailable", "Run the pgvector setup command first"
        )


def setup(database):
    if database.sqlite:
        raise ValueError("pgvector setup requires PostgreSQL")
    with database.write("pgvector-setup") as db:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
        db.execute(text("CREATE SCHEMA IF NOT EXISTS nexus_vectors"))
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS nexus_vectors.entries (version_id text NOT NULL, model text NOT NULL, ordinal integer NOT NULL, snapshot_hash text NOT NULL, embedding public.vector NOT NULL, PRIMARY KEY(version_id, model, ordinal))"
            )
        )
        require(db)


def save(db, version, model, payload):
    require(db)
    snapshot_hash = signature(payload)
    db.execute(
        text("DELETE FROM nexus_vectors.entries WHERE version_id=:version AND model=:model"),
        {"version": version, "model": model},
    )
    db.execute(
        text(
            "INSERT INTO nexus_vectors.entries(version_id,model,ordinal,snapshot_hash,embedding) VALUES (:version,:model,:ordinal,:hash,CAST(:embedding AS public.vector))"
        ),
        [
            {
                "version": version,
                "model": model,
                "ordinal": i,
                "hash": snapshot_hash,
                "embedding": json.dumps(vector),
            }
            for i, vector in enumerate(json.loads(payload))
        ],
    )


def rank(database, version, model, payload, query, limit):
    with database.read() as db:
        require(db)
        params = {
            "version": version,
            "model": model,
            "hash": signature(payload),
            "query": json.dumps(query),
            "limit": limit,
        }
        # Count and ranking share a statement snapshot, including during concurrent rebuilds.
        rows = (
            db.execute(
                text("""
            WITH scoped AS MATERIALIZED (
              SELECT ordinal, embedding FROM nexus_vectors.entries
              WHERE version_id=:version AND model=:model AND snapshot_hash=:hash
            ) SELECT ordinal, 1 - (embedding OPERATOR(public.<=>) CAST(:query AS public.vector)) AS score,
                     (SELECT count(*) FROM scoped) AS total
              FROM scoped ORDER BY embedding OPERATOR(public.<=>) CAST(:query AS public.vector), ordinal LIMIT :limit
        """),
                params,
            )
            .mappings()
            .all()
        )
        if not rows or rows[0]["total"] != len(json.loads(payload)):
            raise GatewayError(
                409, "pgvector_rebuild_required", "Rebuild this index with pgvector enabled"
            )
        return rows
