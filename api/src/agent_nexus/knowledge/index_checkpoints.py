"""Private, job-scoped embedding progress; never exposed as a searchable index."""

import json
import time

from sqlalchemy import select

from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata

checkpoints = metadata.tables["knowledge_index_checkpoints"]
jobs = metadata.tables["knowledge_index_jobs"]


class IndexCheckpoint:
    def __init__(self, database, task):
        self.database, self.task = database, task

    def guard(self, db):
        # Conditional write locks the job row against reclaim until this transaction ends.
        result = db.execute(
            jobs.update()
            .where(
                jobs.c.id == self.task["id"],
                jobs.c.status == "processing",
                jobs.c.claim_token == self.task["claim_token"],
                jobs.c.lease_until > int(time.time()),
            )
            .values(claim_token=self.task["claim_token"])
        )
        if result.rowcount != 1:
            raise GatewayError(409, "index_lease_lost", "Index worker lease is no longer valid")

    def load(self, content_revision, model_revision):
        with self.database.write("index-queue") as db:
            self.guard(db)
            row = (
                db.execute(select(checkpoints).where(checkpoints.c.job_id == self.task["id"]))
                .mappings()
                .first()
            )
            if row and (row["content_revision"], row["model_revision"]) == (
                content_revision,
                model_revision,
            ):
                return json.loads(row["payload"]), row["dimensions"]
            db.execute(checkpoints.delete().where(checkpoints.c.job_id == self.task["id"]))
            return [], None

    def save(self, content_revision, model_revision, payload, dimensions):
        serialized = json.dumps(payload, separators=(",", ":"))
        if len(serialized) > 16 * 1024 * 1024:
            raise GatewayError(409, "index_capacity", "Index checkpoint exceeds 16 MiB")
        with self.database.write("index-queue") as db:
            self.guard(db)
            db.execute(checkpoints.delete().where(checkpoints.c.job_id == self.task["id"]))
            db.execute(
                checkpoints.insert().values(
                    job_id=self.task["id"],
                    content_revision=content_revision,
                    model_revision=model_revision,
                    dimensions=dimensions,
                    payload=serialized,
                )
            )
