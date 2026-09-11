"""Explicit bounded vector builds and exact cosine retrieval of published content."""

import asyncio
import hashlib
import json
import math

from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from agent_nexus.applications.store import ApplicationStore
from agent_nexus.core.errors import GatewayError
from agent_nexus.core.schemas import StrictModel
from agent_nexus.models.schemas import EmbeddingRequest
from agent_nexus.models.store import ModelStore
from agent_nexus.storage.database import metadata
from agent_nexus.tenants.store import TenantStore
from .search import readable_chunks

indexes = metadata.tables["knowledge_vector_indexes"]
MAX_INDEX_CHUNKS = 128
MAX_DIMENSIONS = 4096


class IndexRequest(StrictModel):
    model: str = Field(min_length=1, max_length=64)


class VectorSearchRequest(IndexRequest):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=20, strict=True)


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def unit(vector):
    if not vector or len(vector) > MAX_DIMENSIONS or any(not math.isfinite(n) for n in vector):
        raise GatewayError(
            502, "invalid_index_vector", "Embedding dimensions or values are invalid"
        )
    norm = math.hypot(*vector)
    if not norm or not math.isfinite(norm):
        raise GatewayError(502, "invalid_index_vector", "Embedding must have a finite nonzero norm")
    return [value / norm for value in vector]


class VectorService:
    def __init__(self, database, gateway):
        self.database = database
        self.gateway = gateway

    def snapshot(self, tenant, app, version, model):
        rows = readable_chunks(self.database, tenant, app, version)
        if model not in TenantStore(self.database).allowed(tenant):
            raise GatewayError(403, "model_not_allowed", "Model is not assigned to this tenant")
        config = self.gateway.resolve(model, "embeddings")
        return rows, config

    def validate_snapshot(self, tenant, app, version, model, content_hash, model_hash):
        rows, config = self.snapshot(tenant, app, version, model)
        if fingerprint(rows) != content_hash or ModelStore.etag(config) != model_hash:
            raise GatewayError(
                409,
                "index_stale",
                "Published content or model configuration changed; rebuild the index",
            )
        return rows

    def load(self, version, model):
        with self.database.read() as db:
            row = (
                db.execute(
                    select(indexes).where(indexes.c.version_id == version, indexes.c.model == model)
                )
                .mappings()
                .first()
            )
            if not row:
                raise GatewayError(409, "index_missing", "Build this version/model index first")
            return dict(row)

    def describe(self, tenant, app, version, model):
        rows, config = self.snapshot(tenant, app, version, model)
        index = self.load(version, model)
        return {
            "model": model,
            "version_id": version,
            "dimensions": index["dimensions"],
            "chunks": len(json.loads(index["payload"])),
            "status": "ready"
            if fingerprint(rows) == index["content_fingerprint"]
            and ModelStore.etag(config) == index["model_fingerprint"]
            else "stale",
        }

    async def build(self, tenant, app, version, model, actor, request_id, on_save=None):
        rows, config = await run_in_threadpool(self.snapshot, tenant, app, version, model)
        if not rows or len(rows) > MAX_INDEX_CHUNKS:
            raise GatewayError(409, "index_capacity", "Indexing requires 1..128 published chunks")
        content_hash, model_hash = fingerprint(rows), ModelStore.etag(config)
        payload = []
        dimensions = None
        try:
            async with asyncio.timeout(120):
                for start in range(0, len(rows), 16):
                    batch = rows[start : start + 16]
                    request = EmbeddingRequest(model=model, input=[row["text"] for row in batch])
                    result = await self.gateway.embed_config(
                        config, request, request_id, tenant_id=tenant
                    )
                    if dimensions is not None and result.dimensions != dimensions:
                        raise GatewayError(
                            502,
                            "embedding_dimensions_changed",
                            "Embedding dimensions changed between batches",
                        )
                    dimensions = result.dimensions
                    payload.extend(unit(vector) for vector in result.vectors)
        except TimeoutError:
            raise GatewayError(
                504, "index_build_timeout", "Index build exceeded 120 seconds"
            ) from None
        await run_in_threadpool(
            self.validate_snapshot, tenant, app, version, model, content_hash, model_hash
        )
        serialized = json.dumps(payload, separators=(",", ":"))
        if len(serialized) > 16 * 1024 * 1024:
            raise GatewayError(409, "index_capacity", "Index payload exceeds 16 MiB")

        def save():
            with self.database.write("application:" + app) as db:
                if on_save:
                    on_save(db)
                db.execute(
                    indexes.delete().where(
                        indexes.c.version_id == version, indexes.c.model == model
                    )
                )
                db.execute(
                    indexes.insert().values(
                        version_id=version,
                        model=model,
                        model_fingerprint=model_hash,
                        content_fingerprint=content_hash,
                        dimensions=dimensions,
                        payload=serialized,
                    )
                )
                ApplicationStore.record(
                    db, app, actor, request_id, "vector_index_built:" + model, version
                )

        await run_in_threadpool(save)
        return {
            "model": model,
            "version_id": version,
            "dimensions": dimensions,
            "chunks": len(rows),
        }

    async def search(self, tenant, app, version, body, request_id):
        if not body.query.strip():
            raise GatewayError(422, "invalid_query", "Query must not be blank")
        rows, config = await run_in_threadpool(self.snapshot, tenant, app, version, body.model)
        index = await run_in_threadpool(self.load, version, body.model)
        model_hash, content_hash = ModelStore.etag(config), fingerprint(rows)
        if model_hash != index["model_fingerprint"] or content_hash != index["content_fingerprint"]:
            raise GatewayError(
                409,
                "index_stale",
                "Published content or model configuration changed; rebuild the index",
            )
        embedded = await self.gateway.embed_config(
            config,
            EmbeddingRequest(model=body.model, input=[body.query]),
            request_id,
            tenant_id=tenant,
        )
        query = unit(embedded.vectors[0])
        if len(query) != index["dimensions"]:
            raise GatewayError(
                409, "index_stale", "Embedding dimensions changed; rebuild the index"
            )
        # Recheck after network I/O, so withdrawal or grant revocation while awaiting the model is honored.
        rows = await run_in_threadpool(
            self.validate_snapshot, tenant, app, version, body.model, content_hash, model_hash
        )
        vectors = json.loads(index["payload"])
        results = [
            {
                **row,
                "version_id": version,
                "score": sum(a * b for a, b in zip(query, vector, strict=True)),
            }
            for row, vector in zip(rows, vectors, strict=True)
        ]
        results.sort(key=lambda row: (-row["score"], row["document_id"], row["chunk_index"]))
        return {"data": results[: body.limit], "method": "vector_cosine", "model": body.model}
