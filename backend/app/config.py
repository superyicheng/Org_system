from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Small local-first configuration for the hackathon demo."""

    database_path: Path
    app_name: str = "Org_system"
    memory_engine: str = "SYNAPSE-compatible SQLite graph"


def get_settings() -> Settings:
    app_dir = Path(__file__).resolve().parents[1]
    data_dir = app_dir / "data"
    return Settings(database_path=data_dir / "org_system.sqlite3")
