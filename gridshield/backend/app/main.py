"""
BlackoutFree FastAPI application entry point.

Wires together all routers, middleware, startup/shutdown handlers,
and exposes the ASGI app object used by uvicorn.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.LOG_LEVEL)
    # Import here to avoid circular imports at module load time
    from app.db.session import create_db_and_tables
    await create_db_and_tables()
    from app.db import repository
    from app.db.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        await repository.mark_unfinished_runs_failed(session)
    yield
    # Cleanup on shutdown
    from app.db.session import engine
    await engine.dispose()


app = FastAPI(
    title="BlackoutFree API",
    version="1.0.0",
    description="City grid resilience digital twin with priority-aware demand response",
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": detail}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": details,
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled API error",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred",
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.metrics import router as metrics_router  # noqa: E402
from app.api.runs import router as runs_router  # noqa: E402
from app.api.scenarios import router as scenarios_router  # noqa: E402
from app.api.websocket import router as ws_router  # noqa: E402

app.include_router(scenarios_router, prefix=settings.API_V1_PREFIX)
app.include_router(runs_router,      prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router,   prefix=settings.API_V1_PREFIX)
app.include_router(ws_router,        prefix=settings.API_V1_PREFIX)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", tags=["system"], response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="1.0.0")
