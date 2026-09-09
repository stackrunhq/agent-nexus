from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    CheckConstraint,
)


def define_application_tables(metadata):
    Table(
        "applications",
        metadata,
        Column("id", Text, primary_key=True),
        Column("tenant_id", Text, ForeignKey("tenants.id"), nullable=False, index=True),
        Column("slug", Text, nullable=False),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False),
        Column("enabled", Integer, nullable=False, server_default="1"),
        UniqueConstraint("tenant_id", "slug", name="uq_application_tenant_slug"),
    )
    Table(
        "application_versions",
        metadata,
        Column("id", Text, primary_key=True),
        Column("application_id", Text, ForeignKey("applications.id"), nullable=False, index=True),
        Column("version", Text, nullable=False),
        Column("notes", Text, nullable=False),
        Column("status", Text, nullable=False, server_default="draft"),
        UniqueConstraint("application_id", "version", name="uq_application_version"),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')", name="ck_application_version_status"
        ),
    )
    Table(
        "application_events",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("application_id", Text, ForeignKey("applications.id"), nullable=False, index=True),
        Column("version_id", Text),
        Column("actor", Text, nullable=False),
        Column("action", Text, nullable=False),
        Column("request_id", Text, nullable=False),
        Column("created_at", BigInteger, nullable=False),
    )
