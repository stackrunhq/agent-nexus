"""Run explicit schema upgrades and copy a stopped SQLite database to empty storage."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from importlib.resources import files
from urllib.parse import quote

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from agent_nexus.storage.database import Database, connection_url, metadata, run
from agent_nexus.models.schemas import ModelConfig


def upgrade(target):
    database = Database(target, prepare=False)
    try:
        config = Config()
        config.set_main_option("script_location", str(files("agent_nexus.storage.migrations")))
        with database.write("schema") as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        database.close()


def digest(connection, table):
    result = hashlib.sha256()
    rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
    for row in rows:
        normalized = {key: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                      if isinstance(value, (bytes, memoryview)) else value for key, value in row.items()}
        result.update(json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode())
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
                    "LOCK TABLE "
                    + ", ".join(table.name for table in tables)
                    + " IN ACCESS EXCLUSIVE MODE"
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
                while batch := rows.fetchmany(1 if table.name == "knowledge_documents" else 500):
                    if table.name == "models":
                        for row in batch:
                            if ModelConfig.model_validate_json(row["config"]).alias != row["alias"]:
                                raise ValueError("Source model alias does not match configuration")
                    dst.execute(table.insert(), [dict(row) for row in batch])
                    counts[table.name] += len(batch)
                if digest(src, table) != digest(dst, table):
                    raise RuntimeError("Imported table verification failed")
            if not destination.sqlite:
                for name in ("model_audit", "tenant_events", "user_events", "application_events"):
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
    parser.add_argument("operation", choices=["upgrade", "import-sqlite", "check"])
    parser.add_argument("--source", help="Existing SQLite file; required for import-sqlite")
    args = parser.parse_args()
    target = os.getenv("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db")
    try:
        if args.operation == "check":
            print(json.dumps(check(target)))
        elif args.operation == "upgrade":
            upgrade(target)
            print("Database upgraded to revision 0006")
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


def check(target):
    # Do not create a SQLite file or its parent directories during diagnostics.
    if "://" not in target and not Path(target).is_file():
        raise ValueError("SQLite database does not exist")
    if target.startswith("sqlite:"):
        from sqlalchemy.engine import make_url

        url = make_url(target)
        if url.query or not url.database or not Path(url.database).is_file():
            raise ValueError("Use an existing ordinary SQLite file for diagnostics")
    database = Database(target, prepare=False)
    try:
        return database.check()
    finally:
        database.close()


if __name__ == "__main__":
    main()
