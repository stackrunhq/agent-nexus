"""Private, job-scoped embedding progress; never exposed as a searchable index."""

import json
import time

from sqlalchemy import select, func

from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import metadata

checkpoints = metadata.tables["knowledge_index_checkpoints"]
jobs = metadata.tables["knowledge_index_jobs"]
batches = metadata.tables["knowledge_index_batches"]


def clear(db, job_ids):
    db.execute(batches.delete().where(batches.c.job_id.in_(job_ids)))
    db.execute(checkpoints.delete().where(checkpoints.c.job_id.in_(job_ids)))


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
                payload = []
                for batch in db.execute(
                    select(batches)
                    .where(batches.c.job_id == self.task["id"])
                    .order_by(batches.c.start)
                ).mappings():
                    if batch["start"] != len(payload):
                        raise GatewayError(
                            409, "index_checkpoint_invalid", "Non-contiguous batches"
                        )
                    payload.extend(json.loads(batch["payload"]))
                return payload, row["dimensions"]
            clear(db, [self.task["id"]])
            return [], None

    def save(self, content_revision, model_revision, payload, dimensions, *, start=0):
        serialized = json.dumps(payload, separators=(",", ":"))
        if not 1 <= len(payload) <= 16 or start < 0 or start + len(payload) > 128:
            raise GatewayError(409, "index_capacity", "Invalid checkpoint batch size")
        if len(serialized) > 16 * 1024 * 1024:
            raise GatewayError(409, "index_capacity", "Index checkpoint exceeds 16 MiB")
        with self.database.write("index-queue") as db:
            self.guard(db)
            if start == 0:
                clear(db, [self.task["id"]])
                db.execute(
                    checkpoints.insert().values(
                        job_id=self.task["id"],
                        content_revision=content_revision,
                        model_revision=model_revision,
                        dimensions=dimensions,
                        payload="[]",
                    )
                )
            else:
                row = (
                    db.execute(select(checkpoints).where(checkpoints.c.job_id == self.task["id"]))
                    .mappings()
                    .first()
                )
                if not row or (
                    row["content_revision"],
                    row["model_revision"],
                    row["dimensions"],
                ) != (content_revision, model_revision, dimensions):
                    raise GatewayError(
                        409, "index_checkpoint_invalid", "Checkpoint revision mismatch"
                    )
                previous = (
                    db.execute(
                        select(batches)
                        .where(batches.c.job_id == self.task["id"])
                        .order_by(batches.c.start.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if (
                    not previous
                    or previous["start"] + len(json.loads(previous["payload"])) != start
                ):
                    raise GatewayError(
                        409, "index_checkpoint_invalid", "Non-contiguous batch append"
                    )
            size = db.execute(
                select(func.coalesce(func.sum(func.length(batches.c.payload)), 0)).where(
                    batches.c.job_id == self.task["id"]
                )
            ).scalar_one()
            if size + len(serialized) > 16 * 1024 * 1024:
                raise GatewayError(409, "index_capacity", "Index checkpoints exceed 16 MiB")
            db.execute(
                batches.insert().values(job_id=self.task["id"], start=start, payload=serialized)
            )
