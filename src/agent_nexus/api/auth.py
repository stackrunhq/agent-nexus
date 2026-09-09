import secrets
from typing import Annotated
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from agent_nexus.core.errors import GatewayError


def authentication(settings):
    bearer = HTTPBearer(auto_error=False)

    def admin_auth(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not credentials or not secrets.compare_digest(
            credentials.credentials.encode(), settings.admin_token.encode()
        ):
            raise GatewayError(401, "unauthorized", "Valid administrator token required")

    def client_auth(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if not credentials:
            raise GatewayError(401, "unauthorized", "Valid client token required")
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
