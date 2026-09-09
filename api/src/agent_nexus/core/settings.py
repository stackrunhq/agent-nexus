import os
from dataclasses import dataclass


@dataclass
class Settings:
    admin_token: str
    client_token: str
    database_path: str
    allowed_hosts: set[str]
    auth_mode: str = "bootstrap"
    database_url: str | None = None

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("NEXUS_ADMIN_TOKEN", ""),
            os.getenv("NEXUS_CLIENT_TOKEN", ""),
            os.getenv("NEXUS_DATABASE_PATH", "data/nexus.db"),
            {
                h.strip().lower()
                for h in os.getenv(
                    "NEXUS_ALLOWED_HOSTS", "localhost,127.0.0.1,host.docker.internal"
                ).split(",")
                if h.strip()
            },
            os.getenv("NEXUS_AUTH_MODE", "bootstrap"),
            os.getenv("NEXUS_DATABASE_URL") or None,
        )

    def validate(self):
        if self.auth_mode not in {"bootstrap", "tenant"}:
            raise RuntimeError("NEXUS_AUTH_MODE must be bootstrap or tenant")
        if len(self.admin_token) < 32 or (
            self.auth_mode == "bootstrap" and len(self.client_token) < 32
        ):
            raise RuntimeError(
                "Configure separate NEXUS_ADMIN_TOKEN and NEXUS_CLIENT_TOKEN of at least 32 characters"
            )
        if self.admin_token == self.client_token:
            raise RuntimeError("Admin and client tokens must differ")
