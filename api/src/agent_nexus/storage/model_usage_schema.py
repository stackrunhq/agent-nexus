from sqlalchemy import Column, ForeignKey, Integer, Table, Text, Index


def define_model_usage_tables(metadata):
    table = Table(
        "model_calls",
        metadata,
        Column("id", Text, primary_key=True),
        Column("tenant_id", Text, ForeignKey("tenants.id"), nullable=False),
        Column("request_id", Text, nullable=False),
        Column("index_job_id", Text),
        Column("model", Text, nullable=False),
        Column("model_fingerprint", Text, nullable=False),
        Column("capability", Text, nullable=False),
        Column("created_at", Integer, nullable=False),
        Column("status", Text, nullable=False),
        Column("elapsed_ms", Integer),
        Column("input_tokens", Integer),
        Column("output_tokens", Integer),
        Column("error", Text),
    )
    Index("ix_model_calls_tenant_created", table.c.tenant_id, table.c.created_at)
    Index("ix_model_calls_tenant_job", table.c.tenant_id, table.c.index_job_id)
