from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_quota_tables(metadata):
    Table(
        "tenant_index_quotas",
        metadata,
        Column("tenant_id", Text, ForeignKey("tenants.id"), primary_key=True),
        Column("daily_limit", Integer),
        Column("active_limit", Integer),
    )
