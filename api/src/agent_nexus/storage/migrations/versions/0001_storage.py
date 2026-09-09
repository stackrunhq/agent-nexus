"""Initial model/tenant storage; also adopts the legacy SQLite layout."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Frozen revision schema: never import evolving application metadata here.
    definitions = {
        "models": [
            sa.Column("alias", sa.Text, primary_key=True),
            sa.Column("config", sa.Text, nullable=False),
        ],
        "model_audit": [
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.Column("actor", sa.Text, nullable=False),
            sa.Column("action", sa.Text, nullable=False),
            sa.Column("alias", sa.Text, nullable=False),
            sa.Column("changed_fields", sa.Text, nullable=False),
            sa.Column("request_id", sa.Text),
        ],
        "tenants": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
            sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        ],
        "tenant_models": [
            sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.id"), primary_key=True),
            sa.Column("alias", sa.Text, sa.ForeignKey("models.alias"), primary_key=True),
        ],
        "tenant_events": [
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.Column("tenant_id", sa.Text, nullable=False),
            sa.Column("action", sa.Text, nullable=False),
            sa.Column("alias", sa.Text),
        ],
    }
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for name, columns in definitions.items():
        if name in existing:
            if op.get_bind().dialect.name != "sqlite":
                raise RuntimeError("Refusing to adopt an unversioned non-SQLite schema")
            actual = {column["name"] for column in inspector.get_columns(name)}
            if actual != {column.name for column in columns}:
                raise RuntimeError("Legacy schema does not match expected columns")
        else:
            op.create_table(name, *columns)
    indices = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("model_audit")}
    if "ix_model_audit_alias_id" not in indices:
        op.create_index("ix_model_audit_alias_id", "model_audit", ["alias", "id"])


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
