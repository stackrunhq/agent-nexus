import time
from uuid import uuid4
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import run


class ApplicationStore:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def tenant(db, tenant_id, active=False):
        row = run(db, "SELECT enabled FROM tenants WHERE id=:id", id=tenant_id).first()
        if not row:
            raise GatewayError(404, "tenant_not_found", "Tenant does not exist")
        if active and not row[0]:
            raise GatewayError(409, "tenant_disabled", "Enable the tenant first")

    @staticmethod
    def application(db, tenant_id, app_id, public=False):
        row = (
            run(
                db,
                "SELECT a.* FROM applications a JOIN tenants t ON t.id=a.tenant_id "
                "WHERE a.id=:id AND a.tenant_id=:tenant"
                + (" AND a.enabled=1 AND t.enabled=1" if public else ""),
                id=app_id,
                tenant=tenant_id,
            )
            .mappings()
            .first()
        )
        if not row:
            raise GatewayError(404, "application_not_found", "Application does not exist")
        return {**row, "enabled": bool(row["enabled"])}

    @staticmethod
    def record(db, app_id, actor, request_id, action, version_id=None):
        run(
            db,
            "INSERT INTO application_events(application_id,version_id,actor,request_id,action,created_at) "
            "VALUES (:app,:version,:actor,:request,:action,:now)",
            app=app_id,
            version=version_id,
            actor=actor,
            request=request_id,
            action=action,
            now=int(time.time()),
        )

    def create(self, tenant_id, body, actor, request_id):
        with self.database.write("applications:" + tenant_id) as db:
            self.tenant(db, tenant_id, active=True)
            if run(
                db,
                "SELECT id FROM applications WHERE tenant_id=:tenant AND slug=:slug",
                tenant=tenant_id,
                slug=body.slug,
            ).first():
                raise GatewayError(
                    409, "application_exists", "Application slug already exists in this tenant"
                )
            app_id = str(uuid4())
            run(
                db,
                "INSERT INTO applications(id,tenant_id,slug,name,description) VALUES (:id,:tenant,:slug,:name,:description)",
                id=app_id,
                tenant=tenant_id,
                **body.model_dump(),
            )
            self.record(db, app_id, actor, request_id, "created")
            return self.application(db, tenant_id, app_id)

    def list(self, tenant_id, public=False):
        with self.database.read() as db:
            self.tenant(db, tenant_id)
            return [
                {**row, "enabled": bool(row["enabled"])}
                for row in run(
                    db,
                    "SELECT a.* FROM applications a JOIN tenants t ON t.id=a.tenant_id WHERE a.tenant_id=:tenant"
                    + (" AND a.enabled=1 AND t.enabled=1" if public else "")
                    + " ORDER BY a.slug",
                    tenant=tenant_id,
                ).mappings()
            ]

    def status(self, tenant_id, app_id, enabled, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            current = self.application(db, tenant_id, app_id)
            if current["enabled"] != enabled:
                run(
                    db,
                    "UPDATE applications SET enabled=:enabled WHERE id=:id",
                    id=app_id,
                    enabled=int(enabled),
                )
                self.record(db, app_id, actor, request_id, "enabled" if enabled else "disabled")
            return self.application(db, tenant_id, app_id)

    def versions(self, tenant_id, app_id, public=False):
        with self.database.read() as db:
            self.application(db, tenant_id, app_id, public=public)
            return [
                dict(row)
                for row in run(
                    db,
                    "SELECT * FROM application_versions WHERE application_id=:app"
                    + (" AND status='published'" if public else "")
                    + " ORDER BY version",
                    app=app_id,
                ).mappings()
            ]

    def create_version(self, tenant_id, app_id, body, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            self.application(db, tenant_id, app_id)
            if run(
                db,
                "SELECT id FROM application_versions WHERE application_id=:app AND version=:version",
                app=app_id,
                version=body.version,
            ).first():
                raise GatewayError(
                    409, "version_exists", "Version already exists in this application"
                )
            version_id = str(uuid4())
            run(
                db,
                "INSERT INTO application_versions(id,application_id,version,notes) VALUES (:id,:app,:version,:notes)",
                id=version_id,
                app=app_id,
                **body.model_dump(),
            )
            self.record(db, app_id, actor, request_id, "version_created", version_id)
            return {
                "id": version_id,
                "application_id": app_id,
                "status": "draft",
                **body.model_dump(),
            }

    def transition(self, tenant_id, app_id, version_id, status, actor, request_id):
        with self.database.write("application:" + app_id) as db:
            app = self.application(db, tenant_id, app_id)
            row = (
                run(
                    db,
                    "SELECT * FROM application_versions WHERE id=:id AND application_id=:app",
                    id=version_id,
                    app=app_id,
                )
                .mappings()
                .first()
            )
            if not row:
                raise GatewayError(404, "version_not_found", "Version does not exist")
            if row["status"] == status:
                return dict(row)
            if (row["status"], status) not in {("draft", "published"), ("published", "retired")}:
                raise GatewayError(
                    409, "invalid_transition", "Allowed lifecycle: draft -> published -> retired"
                )
            if status == "published":
                self.tenant(db, tenant_id, active=True)
                if not app["enabled"]:
                    raise GatewayError(
                        409, "application_disabled", "Enable the application before publishing"
                    )
            run(
                db,
                "UPDATE application_versions SET status=:status WHERE id=:id",
                status=status,
                id=version_id,
            )
            self.record(db, app_id, actor, request_id, "version_" + status, version_id)
            return {**row, "status": status}

    def events(self, tenant_id, app_id):
        with self.database.read() as db:
            self.application(db, tenant_id, app_id)
            return [
                dict(row)
                for row in run(
                    db,
                    "SELECT * FROM application_events WHERE application_id=:app ORDER BY id DESC LIMIT 100",
                    app=app_id,
                ).mappings()
            ]
