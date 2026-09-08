import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ModelConfig


class ConfigurationConflict(Exception):
    """The configuration no longer matches the caller's snapshot."""


class ModelStore:
    """Bootstrap configuration storage; never stores provider secrets."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS models (alias TEXT PRIMARY KEY, config TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS model_audit ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
                "actor TEXT NOT NULL, action TEXT NOT NULL, alias TEXT NOT NULL, "
                "changed_fields TEXT NOT NULL, request_id TEXT)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_model_audit_alias_id ON model_audit(alias, id)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def list(self) -> list[ModelConfig]:
        with self.connect() as db:
            return [
                ModelConfig.model_validate_json(row[0])
                for row in db.execute("SELECT config FROM models ORDER BY alias")
            ]

    def get(self, alias: str) -> ModelConfig | None:
        with self.connect() as db:
            row = db.execute("SELECT config FROM models WHERE alias = ?", (alias,)).fetchone()
        return ModelConfig.model_validate_json(row[0]) if row else None

    @staticmethod
    def etag(config: ModelConfig) -> str:
        # Revalidate defaults too: a float default of 60 must hash like persisted 60.0.
        normalized = ModelConfig.model_validate(config.model_dump()).model_dump(mode="json")
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return '"' + hashlib.sha256(canonical.encode()).hexdigest() + '"'

    def put(
        self,
        config: ModelConfig,
        *,
        expected_etag: str = "*",
        actor: str = "system",
        request_id: str | None = None,
    ):
        with self.connect() as db:
            # Serialize read/modify/audit so the event matches the actual previous value.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT config FROM models WHERE alias = ?", (config.alias,)
            ).fetchone()
            previous_model = ModelConfig.model_validate_json(row[0]) if row else None
            if (row and expected_etag != self.etag(previous_model)) or (
                not row and expected_etag != "*"
            ):
                raise ConfigurationConflict()
            previous = previous_model.model_dump() if row else {}
            current = config.model_dump()
            changed = sorted(key for key, value in current.items() if previous.get(key) != value)
            if row and not changed:
                return
            action = "created" if not row else "updated"
            if row and "enabled" in changed:
                action = "enabled" if config.enabled else "disabled"
            db.execute(
                "INSERT INTO models VALUES (?, ?) ON CONFLICT(alias) DO UPDATE SET config=excluded.config",
                (config.alias, config.model_dump_json()),
            )
            db.execute(
                "INSERT INTO model_audit(created_at, actor, action, alias, changed_fields, request_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    actor,
                    action,
                    config.alias,
                    json.dumps(changed),
                    request_id,
                ),
            )

    def audit(self, *, alias: str | None = None, before: int | None = None, limit: int = 50):
        conditions, params = [], []
        if alias is not None:
            conditions.append("alias = ?")
            params.append(alias)
        if before is not None:
            conditions.append("id < ?")
            params.append(before)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM model_audit" + where + " ORDER BY id DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        data = [
            {**dict(row), "changed_fields": json.loads(row["changed_fields"])}
            for row in rows[:limit]
        ]
        return {"data": data, "next_before": data[-1]["id"] if len(rows) > limit else None}
