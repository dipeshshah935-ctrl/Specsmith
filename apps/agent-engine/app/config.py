from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    """Configuration settings for the Blueprint Engine AI Orchestrator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    USE_MOCK_LLM: bool = False
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MONGODB_URI: Optional[str] = None
    MONGODB_DB_NAME: str = "blueprint_engine"
    MAX_AUTO_RETRIES: int = 2

    @model_validator(mode="after")
    def validate_api_key_when_mock_disabled(self) -> "EngineSettings":
        if not self.USE_MOCK_LLM and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required when USE_MOCK_LLM=False")
        return self
