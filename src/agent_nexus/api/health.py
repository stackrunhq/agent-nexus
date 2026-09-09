from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError
from agent_nexus.core.errors import GatewayError


def health_router():
    router = APIRouter(tags=["Health"])

    @router.get("/health/live")
    def health():
        return {"status": "ok"}

    @router.get("/health/ready")
    def ready(request: Request):
        try:
            request.app.state.gateway.store.database.check()
        except (SQLAlchemyError, RuntimeError):
            raise GatewayError(
                503, "database_not_ready", "Database schema or connection is not ready"
            ) from None
        return {"status": "ok"}

    return router
