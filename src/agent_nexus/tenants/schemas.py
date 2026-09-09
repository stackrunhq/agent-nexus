from pydantic import Field, field_validator
from agent_nexus.core.schemas import StrictModel


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
