import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Small local-first configuration for the hackathon demo."""

    database_path: Path
    app_name: str = "org.system"
    memory_engine: str = "SYNAPSE-compatible SQLite graph"
    llm_mode: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    reverify_interval_seconds: int = 3600


def get_settings() -> Settings:
    app_dir = Path(__file__).resolve().parents[1]
    data_dir = app_dir / "data"
    requested_mode = os.getenv("ORG_SYSTEM_LLM_MODE", "auto").lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    llm_mode = "openai" if requested_mode == "openai" or (requested_mode == "auto" and api_key) else "mock"
    return Settings(
        database_path=Path(os.getenv("ORG_SYSTEM_DB_PATH", data_dir / "org_system.sqlite3")),
        llm_mode=llm_mode,
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        reverify_interval_seconds=max(60, int(os.getenv("ORG_SYSTEM_REVERIFY_SECONDS", "3600"))),
    )
