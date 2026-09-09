from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_nexus.core.errors import GatewayError
from .schemas import Login, PasswordReset, UserCreate, UserStatus


def identity_router(get_store, admin_auth):
    router = APIRouter(prefix="/api/v1", tags=["Personal identity"])
    bearer = HTTPBearer(auto_error=False)

    def session_auth(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        user = get_store().authenticate(credentials.credentials) if credentials else None
        if user is None:
            raise GatewayError(401, "unauthorized", "Valid personal session required")
        request.state.user = user
        request.state.session_token = credentials.credentials
        return user

    @router.post("/auth/login")
    def login(body: Login):
        return get_store().login(body.username, body.password)

    @router.get("/auth/me")
    def me(user: Annotated[dict, Depends(session_auth)]):
        return user

    @router.post("/auth/logout", dependencies=[Depends(session_auth)], status_code=204)
    def logout(request: Request):
        get_store().logout(request.state.session_token, request.state.user["id"])

    @router.post("/admin/users", dependencies=[Depends(admin_auth)], status_code=201)
    def create(body: UserCreate, request: Request):
        return get_store().create(body, request.state.actor)

    @router.get("/admin/users", dependencies=[Depends(admin_auth)])
    def users():
        return {"data": get_store().list()}

    @router.patch("/admin/users/{user_id}", dependencies=[Depends(admin_auth)], status_code=204)
    def status(user_id: str, body: UserStatus, request: Request):
        get_store().update(user_id, request.state.actor, enabled=body.enabled)

    @router.post(
        "/admin/users/{user_id}/reset-password", dependencies=[Depends(admin_auth)], status_code=204
    )
    def reset(user_id: str, body: PasswordReset, request: Request):
        get_store().update(user_id, request.state.actor, password=body.password)

    @router.get("/admin/user-events", dependencies=[Depends(admin_auth)])
    def events():
        return {"data": get_store().events()}

    return router
