import logging
from uuid import uuid4
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from agent_nexus.core.errors import GatewayError


def register_error_handlers(app):
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 -- sanitize unexpected errors at the API boundary
            logging.getLogger(__name__).error(
                "Unhandled request error id=%s", request.state.request_id
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {"code": "internal_error", "message": "Internal server error"},
                    "request_id": request.state.request_id,
                },
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/admin"):
            # Ant Design injects component CSS. Script policy remains self-only.
            style_policy = (
                "style-src 'self' 'unsafe-inline'; "
                if request.url.path == "/admin/tenants"
                or request.url.path.startswith("/admin/assets/tenants/")
                else "style-src 'self'; "
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; "
                + style_policy
                + "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'"
            )
        return response

    @app.exception_handler(GatewayError)
    async def gateway_error(request: Request, exc: GatewayError):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("Database request failed id=%s", request.state.request_id)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database operation unavailable",
                },
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo user prompts, credentials or raw validator input.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request; check the API schema",
                    "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],
                },
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "http_error", "message": str(exc.detail)},
                "request_id": request.state.request_id,
            },
        )
