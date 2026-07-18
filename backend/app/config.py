from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings shared by the API and the local vector store."""

    app_name: str = "Hive.skill API"
    chroma_path: Path = BACKEND_DIR / "data" / "chroma"
    chroma_collection: str = "team_hive_skills"
    llm_api_key: str | None = None
    llm_model: str = "gpt-5.6-luna"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 20.0
    preflight_similarity_threshold: float = 0.35
    retrieve_similarity_threshold: float = 0.35

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="HIVE_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
