"""Tests for sentinel.config.Settings."""

import pytest


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should pick up values from environment variables."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
    monkeypatch.setenv("NEWSAPI_KEY", "news-key-456")
    monkeypatch.setenv("SENTINEL_PRIMARY_MODEL", "google/gemini-3-flash-preview")
    monkeypatch.setenv("SENTINEL_EMBEDDING_MODEL", "google/gemini-embedding-001")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "sentinel_signals")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    from sentinel.config import Settings

    s = Settings()

    assert s.OPENROUTER_API_KEY == "test-key-123"
    assert s.NEWSAPI_KEY == "news-key-456"
    assert s.SENTINEL_PRIMARY_MODEL == "google/gemini-3-flash-preview"
    assert s.SENTINEL_EMBEDDING_MODEL == "google/gemini-embedding-001"
    assert s.QDRANT_URL == "http://localhost:6333"
    assert s.QDRANT_COLLECTION == "sentinel_signals"
    assert s.DEMO_MODE is True
    assert s.demo_mode is True
    assert s.LOG_LEVEL == "DEBUG"


def test_demo_mode_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEMO_MODE should be False when explicitly set to false.

    Note: monkeypatch.delenv is insufficient here because pydantic-settings reads
    DEMO_MODE from the .env file via file I/O (not os.environ), so delenv has no
    effect on the .env file.  Setting the env var to 'false' wins over .env.
    """
    monkeypatch.setenv("DEMO_MODE", "false")

    from sentinel.config import Settings

    s = Settings()
    assert s.DEMO_MODE is False
    assert s.demo_mode is False


def test_get_settings_returns_settings() -> None:
    """get_settings() should return a Settings instance."""
    from sentinel.config import Settings, get_settings

    s = get_settings()
    assert isinstance(s, Settings)
    assert hasattr(s, "OPENROUTER_API_KEY")
    assert hasattr(s, "demo_mode")
