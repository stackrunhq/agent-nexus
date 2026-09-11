from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_model_quota_tables(metadata):
    Table(
        "tenant_model_quotas",
        metadata,
        Column("tenant_id", Text, ForeignKey("tenants.id"), primary_key=True),
        Column("daily_limit", Integer),
    )
