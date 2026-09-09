from typing import Literal
from pydantic import Field, field_validator
from agent_nexus.core.schemas import StrictModel


class ApplicationCreate(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class ApplicationStatus(StrictModel):
    enabled: bool


class VersionCreate(StrictModel):
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
    notes: str = Field(default="", max_length=4000)


class VersionTransition(StrictModel):
    status: Literal["published", "retired"]
