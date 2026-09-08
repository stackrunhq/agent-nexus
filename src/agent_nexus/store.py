import json
import hashlib
from datetime import datetime, timezone
from .database import Database, run

from .schemas import ModelConfig


class ConfigurationConflict(Exception):
    """The configuration no longer matches the caller's snapshot."""


class ModelStore:
    """Bootstrap configuration storage; never stores provider secrets."""

    def __init__(self, path: str | Database):
        self.database = path if isinstance(path, Database) else Database(path)

    def list(self) -> list[ModelConfig]:
        with self.database.read() as db:
            return [
                ModelConfig.model_validate_json(row[0])
                for row in run(db, "SELECT config FROM models ORDER BY alias")
            ]

    def get(self, alias: str) -> ModelConfig | None:
        with self.database.read() as db:
            row = run(db, "SELECT config FROM models WHERE alias = :alias", alias=alias).fetchone()
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
        with self.database.write("model:" + config.alias) as db:
            # Serialize read/modify/audit so the event matches the actual previous value.
            row = run(
                db, "SELECT config FROM models WHERE alias = :alias", alias=config.alias
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
            run(
                db,
                "INSERT INTO models(alias, config) VALUES (:alias, :config) ON CONFLICT(alias) DO UPDATE SET config=excluded.config",
                alias=config.alias,
                config=config.model_dump_json(),
            )
            run(
                db,
                "INSERT INTO model_audit(created_at, actor, action, alias, changed_fields, request_id) "
                "VALUES (:created_at, :actor, :action, :alias, :changed_fields, :request_id)",
                created_at=datetime.now(timezone.utc).isoformat(),
                actor=actor,
                action=action,
                alias=config.alias,
                changed_fields=json.dumps(changed),
                request_id=request_id,
            )

    def audit(self, *, alias: str | None = None, before: int | None = None, limit: int = 50):
        conditions, params = [], {"limit": limit + 1}
        if alias is not None:
            conditions.append("alias = :alias")
            params["alias"] = alias
        if before is not None:
            conditions.append("id < :before")
            params["before"] = before
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.database.read() as db:
            rows = (
                run(
                    db,
                    "SELECT * FROM model_audit" + where + " ORDER BY id DESC LIMIT :limit",
                    **params,
                )
                .mappings()
                .all()
            )
        data = [
            {**dict(row), "changed_fields": json.loads(row["changed_fields"])}
            for row in rows[:limit]
        ]
        return {"data": data, "next_before": data[-1]["id"] if len(rows) > limit else None}
