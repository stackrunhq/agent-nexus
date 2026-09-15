"""Indexes for scoped history and per-model continuation queries."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite bootstrap can already have indexes from current metadata.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_index_history_scope ON knowledge_index_jobs (tenant_id, app_id, version_id, created_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_index_history_model ON knowledge_index_jobs (tenant_id, app_id, version_id, model, created_at DESC, id)"
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
