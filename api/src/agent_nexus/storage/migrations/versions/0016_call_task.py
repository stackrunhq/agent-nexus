"""Persist explicit index task attribution without rewriting historical calls."""

from alembic import op
from sqlalchemy import Column, Text, inspect

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    if "index_job_id" not in {c["name"] for c in inspect(op.get_bind()).get_columns("model_calls")}:
        op.add_column("model_calls", Column("index_job_id", Text, nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_model_calls_tenant_job ON model_calls (tenant_id, index_job_id)"
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
