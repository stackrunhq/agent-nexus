"""Transactional content change counters; authorization is checked separately."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agent_nexus.storage.database import metadata

revisions = metadata.tables["knowledge_content_revisions"]


def current(db, version):
    return (
        db.execute(
            select(revisions.c.revision).where(revisions.c.version_id == version)
        ).scalar_one_or_none()
        or 0
    )


def bump(db, version):
    insert = sqlite_insert if db.dialect.name == "sqlite" else pg_insert
    db.execute(
        insert(revisions)
        .values(version_id=version, revision=1)
        .on_conflict_do_update(
            index_elements=[revisions.c.version_id], set_={"revision": revisions.c.revision + 1}
        )
    )
