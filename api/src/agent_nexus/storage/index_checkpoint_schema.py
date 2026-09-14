from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_index_checkpoint_tables(metadata):
    Table(
        "knowledge_index_checkpoints",
        metadata,
        Column("job_id", Text, ForeignKey("knowledge_index_jobs.id"), primary_key=True),
        Column("content_revision", Text, nullable=False),
        Column("model_revision", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("payload", Text, nullable=False),
    )
