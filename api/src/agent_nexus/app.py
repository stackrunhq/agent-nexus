"""Application assembly. Start reading here, then follow the domain routers."""

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from agent_nexus.core.settings import Settings
from agent_nexus.api.auth import authentication
from agent_nexus.api.errors import register_error_handlers
from agent_nexus.api.health import health_router
from agent_nexus.models.gateway import Gateway
from agent_nexus.models.store import ModelStore
from agent_nexus.models.admin_router import admin_model_router
from agent_nexus.models.client_router import client_model_router
from agent_nexus.tenants.router import tenant_router
from agent_nexus.tenants.store import TenantStore
from agent_nexus.storage.database import Database
from agent_nexus.web.routes import mount_admin
from agent_nexus.identity.store import IdentityStore
from agent_nexus.identity.router import identity_router
from agent_nexus.applications.store import ApplicationStore
from agent_nexus.applications.router import application_router


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        database = Database(settings.database_url or settings.database_path)
        try:
            store = ModelStore(database)
            app.state.tenants = TenantStore(database)
            app.state.identity = IdentityStore(database)
            app.state.applications = ApplicationStore(database)
            async with httpx.AsyncClient(
                transport=transport, follow_redirects=False, trust_env=False
            ) as client:
                app.state.gateway = Gateway(store, client, settings.allowed_hosts)
                yield
        finally:
            database.close()

    app = FastAPI(title="Agent Nexus — Model Gateway", version="0.3.0", lifespan=lifespan)
    admin_auth, client_auth, allowed_models, authorize_model = authentication(settings)
    register_error_handlers(app)
    app.include_router(health_router())
    app.include_router(application_router(lambda: app.state.applications, admin_auth, client_auth))
    app.include_router(identity_router(lambda: app.state.identity, admin_auth))
    app.include_router(tenant_router(lambda: app.state.tenants, admin_auth))
    app.include_router(admin_model_router(settings, admin_auth))
    app.include_router(client_model_router(client_auth, allowed_models, authorize_model))
    mount_admin(app)
    return app
