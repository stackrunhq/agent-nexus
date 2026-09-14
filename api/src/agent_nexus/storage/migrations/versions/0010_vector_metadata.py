import hashlib
import json
from alembic import op
from sqlalchemy import MetaData, inspect, text
from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_vector_metadata_tables(metadata):
    Table(
        "knowledge_vector_metadata",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("model", Text, primary_key=True),
        Column("model_fingerprint", Text, nullable=False),
        Column("content_fingerprint", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("chunks", Integer, nullable=False),
        Column("snapshot_hash", Text, nullable=False),
    )


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("application_versions", schema, Column("id", Text, primary_key=True))
    define_vector_metadata_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_vector_metadata"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing vector metadata schema does not match migration")
    else:
        table.create(db)
    for row in db.execute(
        text(
            "SELECT version_id,model,model_fingerprint,content_fingerprint,dimensions,payload FROM knowledge_vector_indexes"
        ).execution_options(yield_per=1)
    ).mappings():
        values = {
            key: row[key]
            for key in (
                "version_id",
                "model",
                "model_fingerprint",
                "content_fingerprint",
                "dimensions",
            )
        }
        values.update(
            chunks=len(json.loads(row["payload"])),
            snapshot_hash=hashlib.sha256(row["payload"].encode()).hexdigest(),
        )
        db.execute(
            table.delete().where(
                table.c.version_id == row["version_id"], table.c.model == row["model"]
            )
        )
        db.execute(table.insert().values(**values))


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
