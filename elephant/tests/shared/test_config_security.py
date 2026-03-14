"""
Security Test: Ensure sensitive config fields are required (no hardcoded defaults).
Fields: POSTGRES_URL, NEO4J_PASSWORD, AUDITOR_TOKEN_SECRET
"""
import pytest
from pydantic import ValidationError


def test_postgres_url_is_required():
    """POSTGRES_URL must not have a hardcoded default."""
    from shared.config.base import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            NEO4J_PASSWORD="test",
            AUDITOR_TOKEN_SECRET="test"
        )
    assert "POSTGRES_URL" in str(exc_info.value)


def test_neo4j_password_is_required():
    """NEO4J_PASSWORD must not have a hardcoded default."""
    from shared.config.base import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            POSTGRES_URL="postgresql+asyncpg://user:pass@localhost/db",
            AUDITOR_TOKEN_SECRET="test"
        )
    assert "NEO4J_PASSWORD" in str(exc_info.value)


def test_auditor_token_secret_is_required():
    """AUDITOR_TOKEN_SECRET must not have a hardcoded default."""
    from shared.config.base import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            POSTGRES_URL="postgresql+asyncpg://user:pass@localhost/db",
            NEO4J_PASSWORD="test"
        )
    assert "AUDITOR_TOKEN_SECRET" in str(exc_info.value)


def test_settings_loads_from_env(monkeypatch):
    """Settings can be loaded correctly when all required fields are in env."""
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://elephant:securepass@localhost/db")
    monkeypatch.setenv("NEO4J_PASSWORD", "securepass123")
    monkeypatch.setenv("AUDITOR_TOKEN_SECRET", "my-hmac-secret-key-min32chars!!")

    from shared.config.base import Settings
    settings = Settings()
    assert settings.POSTGRES_URL.startswith("postgresql+asyncpg://")
    assert settings.NEO4J_PASSWORD == "securepass123"
    assert settings.AUDITOR_TOKEN_SECRET == "my-hmac-secret-key-min32chars!!"
    # Default fields should still work
    assert settings.LOG_LEVEL == "INFO"
    assert settings.ELEPHANT_ENV == "development"
