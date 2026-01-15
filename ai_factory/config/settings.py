"""Minimal v0 configuration settings for ai_factory.

This module centralizes environment-based configuration such as
PostgreSQL connection parameters and model provider API keys.

It is intentionally small for v0; extend it cautiously as the
project evolves.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class PostgresSettings:
    """Settings for the primary Postgres/pgvector instance.

    Defaults follow the Docker pgvector instance described in the
    project documentation, but can be overridden via environment
    variables.
    """

    host: str = os.getenv("AI_PG_HOST", "localhost")
    port: int = int(os.getenv("AI_PG_PORT", "5433"))
    db: str = os.getenv("AI_PG_DB", "rag_db")
    user: str = os.getenv("AI_PG_USER", "rag_user")
    password: str = os.getenv("AI_PG_PASSWORD", "rag_password")


@dataclass
class ModelProviderSettings:
    """API keys for external model providers (optional).

    For v0 these are just pass-throughs from environment variables.
    """

    dashscope_api_key: Optional[str] = os.getenv("DASHSCOPE_API_KEY")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")


@dataclass
class Settings:
    """Top-level configuration container for ai_factory."""

    postgres: PostgresSettings = PostgresSettings()
    models: ModelProviderSettings = ModelProviderSettings()


# Singleton-style settings instance for convenience imports
settings = Settings()
