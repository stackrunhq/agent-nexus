"""Tenant service credentials and explicit model grants (no user/session system yet)."""

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

from .gateway import GatewayError
from .schemas import StrictModel


class TenantCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Tenant name cannot be blank")
        return value.strip()


class TenantStatus(StrictModel):
    enabled: bool


class TenantStore:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                "enabled INTEGER NOT NULL DEFAULT 1, key_hash TEXT NOT NULL UNIQUE)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS tenant_models (tenant_id TEXT NOT NULL REFERENCES tenants(id), "
                "alias TEXT NOT NULL REFERENCES models(alias), PRIMARY KEY (tenant_id, alias))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS tenant_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "created_at TEXT NOT NULL, tenant_id TEXT NOT NULL, action TEXT NOT NULL, alias TEXT)"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def fingerprint(key):
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def record(db, tenant_id, action, alias=None):
        db.execute(
            "INSERT INTO tenant_events(created_at, tenant_id, action, alias) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), tenant_id, action, alias),
        )

    @staticmethod
    def require(db, tenant_id):
        if not db.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone():
            raise GatewayError(404, "tenant_not_found", "Tenant does not exist")

    def create(self, name):
        tenant_id, key = str(uuid4()), "nx_" + secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute(
                "INSERT INTO tenants(id, name, key_hash) VALUES (?, ?, ?)",
                (tenant_id, name, self.fingerprint(key)),
            )
            self.record(db, tenant_id, "created")
        return {"id": tenant_id, "name": name, "enabled": True, "api_key": key}

    def list(self):
        with self.connect() as db:
            return [
                {**dict(row), "enabled": bool(row["enabled"])}
                for row in db.execute("SELECT id, name, enabled FROM tenants ORDER BY id")
            ]

    def authenticate(self, key):
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM tenants WHERE key_hash = ? AND enabled = 1",
                (self.fingerprint(key),),
            ).fetchone()
        return row["id"] if row else None

    def allowed(self, tenant_id):
        with self.connect() as db:
            return {
                row["alias"]
                for row in db.execute(
                    "SELECT alias FROM tenant_models JOIN tenants ON tenants.id = tenant_models.tenant_id "
                    "WHERE tenant_id = ? AND tenants.enabled = 1",
                    (tenant_id,),
                )
            }

    def grants(self, tenant_id):
        with self.connect() as db:
            self.require(db, tenant_id)
            return [
                row["alias"]
                for row in db.execute(
                    "SELECT alias FROM tenant_models WHERE tenant_id = ? ORDER BY alias",
                    (tenant_id,),
                )
            ]

    def grant(self, tenant_id, alias, enabled):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require(db, tenant_id)
            if enabled:
                if not db.execute("SELECT 1 FROM models WHERE alias = ?", (alias,)).fetchone():
                    raise GatewayError(404, "model_not_found", "Model does not exist")
                result = db.execute(
                    "INSERT OR IGNORE INTO tenant_models VALUES (?, ?)", (tenant_id, alias)
                )
            else:
                result = db.execute(
                    "DELETE FROM tenant_models WHERE tenant_id = ? AND alias = ?",
                    (tenant_id, alias),
                )
            if result.rowcount:
                self.record(db, tenant_id, "model_granted" if enabled else "model_revoked", alias)

    def status(self, tenant_id, enabled):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require(db, tenant_id)
            changed = db.execute(
                "UPDATE tenants SET enabled = ? WHERE id = ? AND enabled != ?",
                (enabled, tenant_id, enabled),
            ).rowcount
            if changed:
                self.record(db, tenant_id, "enabled" if enabled else "disabled")

    def rotate(self, tenant_id):
        key = "nx_" + secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require(db, tenant_id)
            db.execute(
                "UPDATE tenants SET key_hash = ? WHERE id = ?", (self.fingerprint(key), tenant_id)
            )
            self.record(db, tenant_id, "key_rotated")
        return {"id": tenant_id, "api_key": key}

    def events(self, tenant_id):
        with self.connect() as db:
            self.require(db, tenant_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM tenant_events WHERE tenant_id = ? ORDER BY id DESC LIMIT 100",
                    (tenant_id,),
                )
            ]


def tenant_router(get_store, admin_auth):
    router = APIRouter(
        prefix="/api/v1/admin/tenants", tags=["Tenant access"], dependencies=[Depends(admin_auth)]
    )

    @router.post("", status_code=201)
    def create(body: TenantCreate):
        return get_store().create(body.name)

    @router.get("")
    def list_tenants():
        return {"data": get_store().list()}

    @router.patch("/{tenant_id}")
    def set_status(tenant_id: str, body: TenantStatus):
        get_store().status(tenant_id, body.enabled)
        return {"id": tenant_id, "enabled": body.enabled}

    @router.post("/{tenant_id}/rotate-key")
    def rotate(tenant_id: str):
        return get_store().rotate(tenant_id)

    @router.get("/{tenant_id}/models")
    def grants(tenant_id: str):
        return {"data": get_store().grants(tenant_id)}

    @router.put("/{tenant_id}/models/{alias}", status_code=204)
    def grant(tenant_id: str, alias: str):
        get_store().grant(tenant_id, alias, True)

    @router.delete("/{tenant_id}/models/{alias}", status_code=204)
    def revoke(tenant_id: str, alias: str):
        get_store().grant(tenant_id, alias, False)

    @router.get("/{tenant_id}/events")
    def events(tenant_id: str):
        return {"data": get_store().events(tenant_id)}

    return router
