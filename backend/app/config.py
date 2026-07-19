"""Environment-driven settings for local demo and shared cloud deployments."""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _csv(name: str) -> frozenset[str]:
    return frozenset(value.strip().lower() for value in os.getenv(name, "").split(",") if value.strip())


def _origin(value: str) -> str:
    value = value.strip().rstrip("/")
    return value if "://" in value else f"https://{value}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    auth_mode: str
    google_client_id: str
    google_workspace_domain: str
    admin_emails: frozenset[str]
    session_secret: str
    public_url: str
    allowed_origins: tuple[str, ...]
    app_name: str = "Org_system"
    memory_engine: str = "SYNAPSE-compatible PostgreSQL/SQLite graph"

    @property
    def is_demo(self) -> bool:
        return self.auth_mode == "demo"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    backend_dir = Path(__file__).resolve().parents[1]
    local_url = f"sqlite:///{backend_dir / 'data' / 'org_system.sqlite3'}"
    auth_mode = os.getenv("AUTH_MODE", "demo").lower()
    if auth_mode not in {"demo", "google"}:
        raise ValueError("AUTH_MODE must be either 'demo' or 'google'.")
    public_url = _origin(os.getenv("PUBLIC_URL", "http://127.0.0.1:8000"))
    allowed_origins = tuple(_origin(value) for value in os.getenv("ALLOWED_ORIGINS", public_url).split(",") if value.strip())
    database_url = os.getenv("DATABASE_URL", local_url)
    if database_url.startswith("postgres://"):
        database_url = f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    elif database_url.startswith("postgresql://"):
        database_url = f"postgresql+psycopg://{database_url.removeprefix('postgresql://')}"
    settings = Settings(
        database_url=database_url,
        auth_mode=auth_mode,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_workspace_domain=os.getenv("GOOGLE_WORKSPACE_DOMAIN", "").lower().lstrip("@"),
        admin_emails=_csv("ORG_SYSTEM_ADMIN_EMAILS"),
        session_secret=os.getenv("SESSION_SECRET", ""),
        public_url=public_url,
        allowed_origins=allowed_origins,
    )
    if not settings.is_demo and (not settings.google_client_id or not settings.session_secret):
        raise ValueError("Cloud mode requires GOOGLE_CLIENT_ID and SESSION_SECRET.")
    if not settings.is_demo and len(settings.session_secret) < 32:
        raise ValueError("Cloud mode requires SESSION_SECRET with at least 32 characters.")
    return settings
