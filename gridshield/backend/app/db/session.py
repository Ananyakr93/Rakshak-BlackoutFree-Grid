"""
Database session management for GridShield.

Provides an async SQLModel engine, session factory, and table creation.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionFactory = sessionmaker(  # type: ignore[call-overload]
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session():  # type: ignore[return]
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionFactory() as session:
        yield session


async def create_db_and_tables() -> None:
    """Create all SQLModel tables if they don't exist."""
    # Import models to register them with SQLModel metadata
    import app.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.run_sync(_migrate_telemetry_components)


def _migrate_telemetry_components(connection) -> None:
    """Add component telemetry columns to databases created by earlier versions."""
    columns = {
        column["name"]
        for column in inspect(connection).get_columns("telemetry_records")
    }
    for column in ("generation_disturbance_pu", "demand_disturbance_pu"):
        if column not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE telemetry_records ADD COLUMN {column} FLOAT NOT NULL DEFAULT 0"
            )
