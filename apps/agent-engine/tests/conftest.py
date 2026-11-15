import pytest
from app.config import EngineSettings


@pytest.fixture(autouse=True)
def mock_llm_env(monkeypatch):
    """Ensure all pytest test runs default to deterministic offline mock mode unless overridden."""
    monkeypatch.setenv("USE_MOCK_LLM", "true")


@pytest.fixture
def mock_settings() -> EngineSettings:
    """Provide an explicit mock settings instance for tests."""
    return EngineSettings(USE_MOCK_LLM=True)

