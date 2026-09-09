from typing import Literal

from pydantic import Field, model_validator

from agent_nexus.core.schemas import StrictModel


class Login(StrictModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,63}$")
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Login):
    password: str = Field(min_length=15, max_length=256)
    role: Literal["platform_admin", "tenant_user"]
    tenant_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def role_scope(self):
        if (self.role == "tenant_user") != bool(self.tenant_id):
            raise ValueError("Tenant members need a tenant; platform admins cannot have one")
        return self


class UserStatus(StrictModel):
    enabled: bool


class PasswordReset(StrictModel):
    password: str = Field(min_length=15, max_length=256)
