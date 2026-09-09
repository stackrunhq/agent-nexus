"""Identity table definitions shared by application storage (migrations are frozen)."""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Table, Text


def define_identity_tables(metadata):
    Table(
        "users",
        metadata,
        Column("id", Text, primary_key=True),
        Column("username", Text, nullable=False, unique=True),
        Column("password_hash", Text, nullable=False),
        Column("role", Text, nullable=False),
        Column("tenant_id", Text, ForeignKey("tenants.id")),
        Column("enabled", Integer, nullable=False, server_default="1"),
        Column("failed_attempts", Integer, nullable=False, server_default="0"),
        Column("blocked_until", BigInteger, nullable=False, server_default="0"),
    )
    Table(
        "user_sessions",
        metadata,
        Column("key_hash", Text, primary_key=True),
        Column("user_id", Text, ForeignKey("users.id"), nullable=False, index=True),
        Column("expires_at", BigInteger, nullable=False),
    )
    Table(
        "user_events",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", Text, nullable=False),
        Column("actor", Text, nullable=False),
        Column("action", Text, nullable=False),
        Column("created_at", BigInteger, nullable=False),
    )
