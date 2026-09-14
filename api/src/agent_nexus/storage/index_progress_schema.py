from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_index_progress_tables(metadata):
    Table(
        "knowledge_content_revisions",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("revision", Integer, nullable=False),
    )
    Table(
        "knowledge_index_batches",
        metadata,
        Column("job_id", Text, ForeignKey("knowledge_index_checkpoints.job_id"), primary_key=True),
        Column("start", Integer, primary_key=True),
        Column("payload", Text, nullable=False),
    )
