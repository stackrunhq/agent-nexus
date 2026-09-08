"""Run explicit schema upgrades and copy a stopped SQLite database to empty storage."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from .database import Database, connection_url, metadata, run
from .schemas import ModelConfig


def upgrade(target):
    database = Database(target, prepare=False)
    try:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with database.write("schema") as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        database.close()


def digest(connection, table):
    result = hashlib.sha256()
    rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
    for row in rows:
        result.update(json.dumps(dict(row), sort_keys=True, ensure_ascii=True).encode())
        result.update(b"\n")
    return result.digest()


def import_sqlite(source_path, target):
    source_path = Path(source_path).resolve(strict=True)
    destination_url = connection_url(target)
    if destination_url.get_backend_name() == "sqlite":
        target_path = (destination_url.database or "").removeprefix("file:")
        if Path(target_path).resolve() == source_path:
            raise ValueError("Source and destination must differ")
    # Read-only URI: importing must not create or modify the source database.
    source = Database(
        "sqlite:///file:" + quote(source_path.as_posix(), safe="/:") + "?mode=ro&uri=true",
        prepare=False,
    )
    destination = None
    try:
        destination = Database(target)
        counts = {}
        with source.read() as src, destination.write("import") as dst:
            src.exec_driver_sql("BEGIN")
            tables = metadata.sorted_tables
            if not destination.sqlite:
                # Prevent live writers from racing the empty-target check and sequence reset.
                dst.exec_driver_sql(
                    "LOCK TABLE models, model_audit, tenants, tenant_models, tenant_events IN ACCESS EXCLUSIVE MODE"
                )
            if any(
                dst.execute(select(func.count()).select_from(table)).scalar_one()
                for table in tables
            ):
                raise ValueError(
                    "Destination must be empty; existing data will never be overwritten"
                )
            existing = set(inspect(src).get_table_names())
            if "models" not in existing:
                raise ValueError("Source is not an Agent Nexus database")
            for table in tables:
                counts[table.name] = 0
                if table.name not in existing:
                    continue
                rows = src.execute(select(table)).mappings()
                while batch := rows.fetchmany(500):
                    if table.name == "models":
                        for row in batch:
                            if ModelConfig.model_validate_json(row["config"]).alias != row["alias"]:
                                raise ValueError("Source model alias does not match configuration")
                    dst.execute(table.insert(), [dict(row) for row in batch])
                    counts[table.name] += len(batch)
                if digest(src, table) != digest(dst, table):
                    raise RuntimeError("Imported table verification failed")
            if not destination.sqlite:
                for name in ("model_audit", "tenant_events"):
                    run(
                        dst,
                        "SELECT setval(pg_get_serial_sequence(:table, 'id'), "
                        f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {name}",
                        table=name,
                    )
        return counts
    finally:
        source.close()
        if destination:
            destination.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["upgrade", "import-sqlite"])
    parser.add_argument("--source", help="Existing SQLite file; required for import-sqlite")
    args = parser.parse_args()
    target = os.getenv("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db")
    try:
        if args.operation == "upgrade":
            upgrade(target)
            print("Database upgraded to revision 0001")
        else:
            if not args.source:
                parser.error("--source is required")
            print(json.dumps(import_sqlite(args.source, target)))
    except Exception:
        # Never print connection URLs, SQL parameter values or imported credential hashes.
        parser.exit(
            1,
            "Database operation failed. Check connectivity, schema and empty target; no credentials are printed.\n",
        )


if __name__ == "__main__":
    main()
