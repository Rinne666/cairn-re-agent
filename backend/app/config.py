from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAIRN_", extra="ignore")

    app_name: str = "Cairn RE Engine"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./cairn.db"
    artifact_root: Path = Path("../artifacts")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_workers: int = 3
    intent_lease_seconds: int = 120
    pi_command: str = ""
    reverse_tool_command: str = ""
    max_upload_mb: int = 64

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
