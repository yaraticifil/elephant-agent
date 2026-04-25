from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── REQUIRED secrets (no defaults — must come from env/.env) ──────────────
    POSTGRES_URL: str              # e.g. postgresql+asyncpg://user:pass@host/db
    NEO4J_PASSWORD: str            # Neo4j password — never hardcode
    AUDITOR_TOKEN_SECRET: str      # HMAC signing secret — never hardcode

    # ── Optional with safe defaults ────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://qdrant:6333"
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    ELEPHANT_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DAILY_BUDGET_USD: float = 10.00
    SERVICE_NAME: str = "unknown"
    AGENT_NAME: str = ""
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    ORCHESTRATOR_URL: str = "http://orchestrator:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
