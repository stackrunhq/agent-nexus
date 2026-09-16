"""Record invocation attempt and batch position; historical values stay unknown."""

from alembic import op
from sqlalchemy import Column, Integer, inspect

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_calls")}
    for name in ("index_attempt", "index_batch_start", "index_batch_size"):
        if name not in columns:
            op.add_column("model_calls", Column(name, Integer, nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
