import secrets
from typing import Annotated
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from agent_nexus.core.errors import GatewayError


def authentication(settings):
    bearer = HTTPBearer(auto_error=False)

    def admin_auth(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if not credentials:
            raise GatewayError(401, "unauthorized", "Valid administrator token required")
        token = credentials.credentials
        if secrets.compare_digest(token.encode(), settings.admin_token.encode()):
            request.state.actor = "platform_admin"
            return
        user = request.app.state.identity.authenticate(token)
        if user is None:
            raise GatewayError(401, "unauthorized", "Valid administrator session required")
        if user["role"] != "platform_admin":
            raise GatewayError(403, "forbidden", "Platform administrator role required")
        request.state.actor = user["id"]

    def client_auth(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if not credentials:
            raise GatewayError(401, "unauthorized", "Valid client token required")
        if credentials.credentials.startswith("ns_"):
            user = request.app.state.identity.authenticate(credentials.credentials)
            if user is None:
                raise GatewayError(401, "unauthorized", "Valid personal session required")
            if user["role"] != "tenant_user" or not user["tenant_id"]:
                raise GatewayError(
                    403, "forbidden", "Tenant member role required for model invocation"
                )
            request.state.tenant_id = user["tenant_id"]
            return
        if settings.auth_mode == "tenant":
            tenant_id = request.app.state.tenants.authenticate(credentials.credentials)
            if tenant_id is None:
                raise GatewayError(401, "unauthorized", "Valid tenant credential required")
            request.state.tenant_id = tenant_id
        else:
            if not secrets.compare_digest(
                credentials.credentials.encode(), settings.client_token.encode()
            ):
                raise GatewayError(401, "unauthorized", "Valid client token required")
            request.state.tenant_id = None

    def allowed_models(request: Request):
        if request.state.tenant_id is None:
            return None
        return request.app.state.tenants.allowed(request.state.tenant_id)

    def authorize_model(request: Request, alias: str):
        allowed = allowed_models(request)
        if allowed is not None and alias not in allowed:
            raise GatewayError(403, "model_not_allowed", "Model is not assigned to this tenant")

    return admin_auth, client_auth, allowed_models, authorize_model
