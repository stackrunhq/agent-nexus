from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_vector_metadata_tables(metadata):
    Table(
        "knowledge_vector_metadata",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("model", Text, primary_key=True),
        Column("model_fingerprint", Text, nullable=False),
        Column("content_fingerprint", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("chunks", Integer, nullable=False),
        Column("snapshot_hash", Text, nullable=False),
    )
