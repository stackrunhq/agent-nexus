from sqlalchemy import Column, Integer, Table, Text


def define_index_scheduler_tables(metadata):
    Table(
        "knowledge_index_scheduler",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("last_tenant_id", Text, nullable=False),
    )
