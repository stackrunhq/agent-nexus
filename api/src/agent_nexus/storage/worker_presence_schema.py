from sqlalchemy import Column, Integer, Table, Text


def define_worker_presence_tables(metadata):
    Table(
        "knowledge_index_workers",
        metadata,
        Column("id", Text, primary_key=True),
        Column("strategy", Text, nullable=False),
        Column("last_seen", Integer, nullable=False),
    )
