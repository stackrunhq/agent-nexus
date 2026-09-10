"""Bounded lexical retrieval over currently readable chunks; no model invocation."""

from collections import Counter
import math
import re
import unicodedata

from pydantic import Field, field_validator
from sqlalchemy import select

from agent_nexus.core.errors import GatewayError
from agent_nexus.core.schemas import StrictModel
from agent_nexus.storage.database import metadata
from .store import KnowledgeStore, chunks, documents

MAX_CHUNKS = 5000
MAX_CHARACTERS = 4_000_000


def tokenize(text):
    words = re.findall(
        r"[\u3400-\u9fff]+|[a-z0-9]+", unicodedata.normalize("NFKC", text).casefold()
    )
    result = []
    for word in words:
        if "\u3400" <= word[0] <= "\u9fff":
            result.extend(word)
            result.extend(word[index : index + 2] for index in range(len(word) - 1))
        else:
            result.append(word)
    return result


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=20, strict=True)

    @field_validator("query")
    @classmethod
    def meaningful(cls, value):
        if not tokenize(value):
            raise ValueError("Query must contain Chinese characters, Latin letters or numbers")
        return value.strip()


def search(database, tenant_id, app_id, version_id, body):
    """Scores are relative BM25-style rankings, not relevance probabilities."""
    versions = metadata.tables["application_versions"]
    apps = metadata.tables["applications"]
    tenants = metadata.tables["tenants"]
    with database.read() as db:
        KnowledgeStore.scope(db, tenant_id, app_id, version_id, public=True)
        # Repeat every visibility condition in the content query itself.
        query = (
            select(chunks, documents.c.filename, documents.c.sha256)
            .select_from(
                chunks.join(documents, chunks.c.document_id == documents.c.id)
                .join(versions, documents.c.version_id == versions.c.id)
                .join(apps, versions.c.application_id == apps.c.id)
                .join(tenants, apps.c.tenant_id == tenants.c.id)
            )
            .where(
                tenants.c.id == tenant_id,
                tenants.c.enabled == 1,
                apps.c.id == app_id,
                apps.c.enabled == 1,
                versions.c.id == version_id,
                versions.c.status == "published",
                documents.c.status == "ready",
                documents.c.published == 1,
            )
            .order_by(chunks.c.document_id, chunks.c.chunk_index)
            .limit(MAX_CHUNKS + 1)
        )
        rows = []
        characters = 0
        for row in db.execute(query).mappings():
            characters += len(row["text"])
            if len(rows) == MAX_CHUNKS or characters > MAX_CHARACTERS:
                raise GatewayError(
                    409,
                    "search_scope_too_large",
                    "This version exceeds the lexical search capacity",
                )
            rows.append(dict(row))
    terms = set(tokenize(body.query))
    counts, lengths = [], []
    frequency = Counter()
    for row in rows:
        tokens = tokenize(row["text"])
        relevant = Counter(token for token in tokens if token in terms)
        counts.append(relevant)
        lengths.append(len(tokens))
        frequency.update(relevant.keys())
    average = sum(lengths) / len(lengths) if lengths else 1
    results = []
    for row, count, length in zip(rows, counts, lengths, strict=True):
        score = 0.0
        for term, tf in count.items():
            inverse_frequency = math.log(
                1 + (len(rows) - frequency[term] + 0.5) / (frequency[term] + 0.5)
            )
            score += (
                inverse_frequency * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / (average or 1)))
            )
        if score > 0:
            results.append(
                {
                    **row,
                    "score": round(score, 6),
                    "version_id": version_id,
                    "matched_terms": sorted(count),
                }
            )
    results.sort(key=lambda row: (-row["score"], row["document_id"], row["chunk_index"]))
    return {"data": results[: body.limit], "method": "lexical_bm25", "scanned_chunks": len(rows)}
