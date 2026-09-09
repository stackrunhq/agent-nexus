"""Tenant-scoped document lifecycle and durable, leased work queue."""

import hashlib
import json
import time
from uuid import uuid4

from sqlalchemy import select

from agent_nexus.applications.store import ApplicationStore
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata, run

documents = metadata.tables["knowledge_documents"]
chunks = metadata.tables["knowledge_chunks"]
SUMMARY = [
    column
    for column in documents.c
    if column.name
    not in {
        "content",
        "claim_token",
        "lease_until",
    }
]


class KnowledgeStore:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def scope(db, tenant_id, app_id, version_id, public=False):
        app = ApplicationStore.application(db, tenant_id, app_id, public=public)
        row = run(
            db,
            "SELECT status FROM application_versions WHERE id=:id AND application_id=:app",
            id=version_id,
            app=app_id,
        ).first()
        if not row or (public and row[0] != "published"):
            raise GatewayError(404, "version_not_found", "Version does not exist")
        return app, row[0]

    @staticmethod
    def document(db, version_id, document_id, public=False):
        query = select(*SUMMARY).where(
            documents.c.id == document_id, documents.c.version_id == version_id
        )
        if public:
            query = query.where(documents.c.published == 1, documents.c.status == "ready")
        row = db.execute(query).mappings().first()
        if not row:
            raise GatewayError(404, "document_not_found", "Document does not exist")
        return {**row, "warnings": json.loads(row["warnings"]), "published": bool(row["published"])}

    def upload(self, tenant_id, app_id, version_id, filename, content, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            app, status = self.scope(db, tenant_id, app_id, version_id)
            ApplicationStore.tenant(db, tenant_id, active=True)
            if not app["enabled"] or status != "draft":
                raise GatewayError(
                    409, "version_not_editable", "Upload to an enabled draft version"
                )
            digest = hashlib.sha256(content).hexdigest()
            existing = db.execute(
                select(documents.c.id).where(
                    documents.c.version_id == version_id,
                    documents.c.sha256 == digest,
                    documents.c.filename == filename,
                )
            ).scalar_one_or_none()
            if existing:
                return self.document(db, version_id, existing)
            document_id = str(uuid4())
            db.execute(
                documents.insert().values(
                    id=document_id,
                    version_id=version_id,
                    filename=filename,
                    sha256=digest,
                    content=content,
                    actor=actor,
                    request_id=request_id,
                    created_at=int(time.time()),
                )
            )
            ApplicationStore.record(
                db, app_id, actor, request_id, "document_uploaded:" + document_id, version_id
            )
            return self.document(db, version_id, document_id)

    def list(self, tenant_id, app_id, version_id, *, public=False, offset=0, limit=50):
        with self.database.read() as db:
            self.scope(db, tenant_id, app_id, version_id, public)
            query = select(documents.c.id).where(documents.c.version_id == version_id)
            if public:
                query = query.where(documents.c.published == 1, documents.c.status == "ready")
            ids = (
                db.execute(
                    query.order_by(documents.c.created_at, documents.c.id)
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [self.document(db, version_id, document_id, public) for document_id in ids]

    def get(
        self,
        tenant_id,
        app_id,
        version_id,
        document_id,
        *,
        public=False,
        offset=0,
        limit=50,
        with_chunks=False,
    ):
        with self.database.read() as db:
            self.scope(db, tenant_id, app_id, version_id, public)
            document = self.document(db, version_id, document_id, public)
            if not with_chunks:
                return document
            return [
                dict(row)
                for row in db.execute(
                    select(chunks)
                    .where(chunks.c.document_id == document_id)
                    .order_by(chunks.c.chunk_index)
                    .offset(offset)
                    .limit(limit)
                ).mappings()
            ]

    def publish(self, tenant_id, app_id, version_id, document_id, published, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            self.scope(db, tenant_id, app_id, version_id, public=published)
            current = self.document(db, version_id, document_id)
            if published and current["status"] != "ready":
                raise GatewayError(
                    409, "document_not_ready", "Parse the document before publication"
                )
            if current["published"] != published:
                db.execute(
                    documents.update()
                    .where(documents.c.id == document_id)
                    .values(published=int(published))
                )
                ApplicationStore.record(
                    db,
                    app_id,
                    actor,
                    request_id,
                    ("document_published:" if published else "document_withdrawn:") + document_id,
                    version_id,
                )
            return self.document(db, version_id, document_id)

    def retry(self, tenant_id, app_id, version_id, document_id, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            app, status = self.scope(db, tenant_id, app_id, version_id)
            ApplicationStore.tenant(db, tenant_id, active=True)
            current = self.document(db, version_id, document_id)
            if status == "retired" or not app["enabled"] or current["status"] != "failed":
                raise GatewayError(
                    409,
                    "document_not_retryable",
                    "Only failed documents in active versions may retry",
                )
            db.execute(
                documents.update()
                .where(documents.c.id == document_id)
                .values(status="queued", error=None, attempts=0, claim_token=None, lease_until=0)
            )
            ApplicationStore.record(
                db, app_id, actor, request_id, "document_retried:" + document_id, version_id
            )
            return self.document(db, version_id, document_id)

    def claim(self):
        now = int(time.time())
        with self.database.write("knowledge_queue") as db:
            expired = (documents.c.status == "processing") & (documents.c.lease_until <= now)
            db.execute(
                documents.update()
                .where(expired, documents.c.attempts >= 3)
                .values(
                    status="failed", error="worker_interrupted", claim_token=None, lease_until=0
                )
            )
            row = (
                db.execute(
                    select(documents)
                    .where((documents.c.status == "queued") | expired)
                    .order_by(documents.c.created_at, documents.c.id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                documents.update()
                .where(documents.c.id == row["id"])
                .values(
                    status="processing",
                    claim_token=token,
                    lease_until=now + 300,
                    attempts=row["attempts"] + 1,
                    error=None,
                )
            )
            return {**row, "claim_token": token}

    def finish(self, document_id, token, result=None, error=None):
        with self.database.write("knowledge_queue") as db:
            row = db.execute(
                select(documents.c.id).where(
                    documents.c.id == document_id,
                    documents.c.claim_token == token,
                    documents.c.status == "processing",
                )
            ).first()
            if not row:
                return False  # A replacement worker owns this task; discard stale results.
            if error is None:
                rows = [
                    {
                        "document_id": document_id,
                        "chunk_index": chunk["index"],
                        **{key: value for key, value in chunk.items() if key != "index"},
                    }
                    for chunk in result["chunks"]
                ]
                db.execute(chunks.delete().where(chunks.c.document_id == document_id))
                for start in range(0, len(rows), 100):
                    db.execute(chunks.insert(), rows[start : start + 100])
            db.execute(
                documents.update()
                .where(documents.c.id == document_id)
                .values(
                    status="failed" if error else "ready",
                    error=error,
                    warnings=json.dumps(result.get("warnings", []) if result else []),
                    claim_token=None,
                    lease_until=0,
                )
            )
            return True
