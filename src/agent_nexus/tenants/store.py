import hashlib
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from agent_nexus.storage.database import Database, run
from agent_nexus.core.errors import GatewayError


class TenantStore:
    def __init__(self, target):
        self.database = target if isinstance(target, Database) else Database(target)

    @staticmethod
    def fingerprint(key):
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def record(db, tenant_id, action, alias=None):
        run(
            db,
            "INSERT INTO tenant_events(created_at, tenant_id, action, alias) "
            "VALUES (:created_at, :tenant_id, :action, :alias)",
            created_at=datetime.now(timezone.utc).isoformat(),
            tenant_id=tenant_id,
            action=action,
            alias=alias,
        )

    @staticmethod
    def require(db, tenant_id):
        if not run(db, "SELECT 1 FROM tenants WHERE id = :id", id=tenant_id).first():
            raise GatewayError(404, "tenant_not_found", "Tenant does not exist")

    def create(self, name):
        tenant_id, key = str(uuid4()), "nx_" + secrets.token_urlsafe(32)
        with self.database.write("tenant:" + tenant_id) as db:
            run(
                db,
                "INSERT INTO tenants(id, name, key_hash) VALUES (:id, :name, :key_hash)",
                id=tenant_id,
                name=name,
                key_hash=self.fingerprint(key),
            )
            self.record(db, tenant_id, "created")
        return {"id": tenant_id, "name": name, "enabled": True, "api_key": key}

    def list(self):
        with self.database.read() as db:
            return [
                {**row, "enabled": bool(row["enabled"])}
                for row in run(db, "SELECT id, name, enabled FROM tenants ORDER BY id").mappings()
            ]

    def authenticate(self, key):
        with self.database.read() as db:
            return run(
                db,
                "SELECT id FROM tenants WHERE key_hash = :hash AND enabled = 1",
                hash=self.fingerprint(key),
            ).scalar_one_or_none()

    def allowed(self, tenant_id):
        with self.database.read() as db:
            return set(
                run(
                    db,
                    "SELECT alias FROM tenant_models JOIN tenants ON tenants.id = tenant_models.tenant_id "
                    "WHERE tenant_id = :id AND tenants.enabled = 1",
                    id=tenant_id,
                ).scalars()
            )

    def grants(self, tenant_id):
        with self.database.read() as db:
            self.require(db, tenant_id)
            return list(
                run(
                    db,
                    "SELECT alias FROM tenant_models WHERE tenant_id = :id ORDER BY alias",
                    id=tenant_id,
                ).scalars()
            )

    def grant(self, tenant_id, alias, enabled):
        with self.database.write("tenant:" + tenant_id) as db:
            self.require(db, tenant_id)
            if enabled:
                if not run(db, "SELECT 1 FROM models WHERE alias = :alias", alias=alias).first():
                    raise GatewayError(404, "model_not_found", "Model does not exist")
                result = run(
                    db,
                    "INSERT INTO tenant_models(tenant_id, alias) VALUES (:id, :alias) "
                    "ON CONFLICT(tenant_id, alias) DO NOTHING",
                    id=tenant_id,
                    alias=alias,
                )
            else:
                result = run(
                    db,
                    "DELETE FROM tenant_models WHERE tenant_id = :id AND alias = :alias",
                    id=tenant_id,
                    alias=alias,
                )
            if result.rowcount:
                self.record(db, tenant_id, "model_granted" if enabled else "model_revoked", alias)

    def status(self, tenant_id, enabled):
        with self.database.write("tenant:" + tenant_id) as db:
            self.require(db, tenant_id)
            changed = run(
                db,
                "UPDATE tenants SET enabled = :enabled WHERE id = :id AND enabled != :enabled",
                id=tenant_id,
                enabled=int(enabled),
            ).rowcount
            if changed:
                self.record(db, tenant_id, "enabled" if enabled else "disabled")

    def rotate(self, tenant_id):
        key = "nx_" + secrets.token_urlsafe(32)
        with self.database.write("tenant:" + tenant_id) as db:
            self.require(db, tenant_id)
            run(
                db,
                "UPDATE tenants SET key_hash = :hash WHERE id = :id",
                hash=self.fingerprint(key),
                id=tenant_id,
            )
            self.record(db, tenant_id, "key_rotated")
        return {"id": tenant_id, "api_key": key}

    def events(self, tenant_id):
        with self.database.read() as db:
            self.require(db, tenant_id)
            return [
                dict(row)
                for row in run(
                    db,
                    "SELECT * FROM tenant_events WHERE tenant_id = :id ORDER BY id DESC LIMIT 100",
                    id=tenant_id,
                ).mappings()
            ]
