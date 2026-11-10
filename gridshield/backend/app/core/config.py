"""
Application configuration using pydantic-settings.

Reads from environment variables and an optional .env file.
All simulation tunables are exposed here so no value is hardcoded
in the physics or control modules.
"""

from __future__ import annotations

import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./gridshield.db"
    EXPERIMENT_RESULTS_PATH: str | None = None

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Simulation timing
    SIMULATION_DT_S: float = 0.02          # RK4 integration step (seconds)
    AGENT_SAMPLE_INTERVAL_S: float = Field(default=0.5, gt=0)
    WS_PUSH_INTERVAL_S: float = Field(default=0.5, gt=0)

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> list[str]:
        """Allow CORS_ORIGINS to be supplied as a JSON string in the env."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v  # type: ignore[return-value]


settings = Settings()
