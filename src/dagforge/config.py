from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: Literal["auto", "openai", "ollama", "demo"] = "auto"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    ollama_timeout_seconds: float = Field(default=180, gt=0, le=3600)
    dagforge_host: str = "0.0.0.0"
    dagforge_port: int = 8000
    dagforge_log_level: str = "INFO"
    airflow_dags_dir: Path = Path("generated")
    airflow_ui_url: str = "http://localhost:8080"

    @property
    def resolved_provider(self) -> Literal["openai", "ollama", "demo"]:
        if self.ai_provider != "auto":
            return "demo" if self.ai_provider == "demo" else self.ai_provider
        if self.openai_api_key and self.openai_api_key.strip():
            return "openai"
        if self.ollama_model and self.ollama_model.strip():
            return "ollama"
        return "demo"

    @property
    def ai_enabled(self) -> bool:
        return self.resolved_provider != "demo"

    @property
    def active_model(self) -> str | None:
        if self.resolved_provider == "openai":
            return self.openai_model
        if self.resolved_provider == "ollama":
            return self.ollama_model.strip() if self.ollama_model else None
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
