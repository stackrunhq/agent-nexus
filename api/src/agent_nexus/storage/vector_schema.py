"""Portable small-corpus vector snapshots; not an approximate nearest-neighbor index."""

from sqlalchemy import Column, ForeignKey, Table, Text, Integer


def define_vector_tables(metadata):
    Table(
        "knowledge_vector_indexes",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("model", Text, primary_key=True),
        Column("model_fingerprint", Text, nullable=False),
        Column("content_fingerprint", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("payload", Text, nullable=False),
    )
