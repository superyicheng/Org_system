"""Environment-driven settings for the local demo and shared cloud service."""

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
    allowed_emails: frozenset[str]
    session_secret: str
    public_url: str
    allowed_origins: tuple[str, ...]
    app_name: str = "org.system"
    memory_engine: str = "SYNAPSE-compatible PostgreSQL/SQLite graph with semantic vectors"
    llm_mode: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    reverify_interval_seconds: int = 3600
    # Off by default so enabling multi-org support never silently opens an existing
    # private deployment to every Google account. Set ORG_SELF_SERVE=true to let any
    # verified user sign in and then create or join an organization by invite.
    org_self_serve: bool = False

    @property
    def is_demo(self) -> bool:
        return self.auth_mode == "demo"

    @property
    def is_public_trial(self) -> bool:
        return self.auth_mode == "public"

    @property
    def auto_verifies_personal_memory(self) -> bool:
        return self.is_demo or self.is_public_trial


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    backend_dir = Path(__file__).resolve().parents[1]
    local_url = f"sqlite:///{backend_dir / 'data' / 'org_system.sqlite3'}"
    auth_mode = os.getenv("AUTH_MODE", "demo").lower()
    if auth_mode not in {"demo", "google", "public"}:
        raise ValueError("AUTH_MODE must be 'demo', 'google', or 'public'.")
    public_url = _origin(os.getenv("PUBLIC_URL", "http://127.0.0.1:8000"))
    allowed_origins = tuple(_origin(value) for value in os.getenv("ALLOWED_ORIGINS", public_url).split(",") if value.strip())
    # Keep the pre-cloud test/demo override working while production uses DATABASE_URL.
    legacy_path = os.getenv("ORG_SYSTEM_DB_PATH", "").strip()
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{legacy_path}" if legacy_path else local_url)
    if database_url.startswith("postgres://"):
        database_url = f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    elif database_url.startswith("postgresql://"):
        database_url = f"postgresql+psycopg://{database_url.removeprefix('postgresql://')}"
    requested_mode = os.getenv("ORG_SYSTEM_LLM_MODE", "auto").lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    llm_mode = "openai" if requested_mode == "openai" or (requested_mode == "auto" and api_key) else "mock"
    settings = Settings(
        database_url=database_url,
        auth_mode=auth_mode,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_workspace_domain=os.getenv("GOOGLE_WORKSPACE_DOMAIN", "").lower().lstrip("@"),
        admin_emails=_csv("ORG_SYSTEM_ADMIN_EMAILS"),
        allowed_emails=_csv("ORG_SYSTEM_ALLOWED_EMAILS"),
        session_secret=os.getenv("SESSION_SECRET", ""),
        public_url=public_url,
        allowed_origins=allowed_origins,
        llm_mode=llm_mode,
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
        reverify_interval_seconds=max(60, int(os.getenv("ORG_SYSTEM_REVERIFY_SECONDS", "3600"))),
        org_self_serve=os.getenv("ORG_SELF_SERVE", "").strip().lower() in {"1", "true", "yes", "on"},
    )
    if not settings.is_demo and (not settings.google_client_id or len(settings.session_secret) < 32):
        raise ValueError("Google and public cloud modes require GOOGLE_CLIENT_ID and a SESSION_SECRET of at least 32 characters.")
    return settings
