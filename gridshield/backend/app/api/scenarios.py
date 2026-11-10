"""
REST endpoints for scenario management.

  POST   /api/v1/scenarios        — create a new scenario
  GET    /api/v1/scenarios        — list all scenarios
  GET    /api/v1/scenarios/{id}   — retrieve a single scenario by ID
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import repository
from app.db.session import get_session
from app.schemas.api import (
    ScenarioCreatedResponse,
    ScenarioDetailsResponse,
    ScenarioSummaryResponse,
    ScenarioTemplateResponse,
)
from app.schemas.scenario import ScenarioConfig

router = APIRouter(tags=["scenarios"])
logger = logging.getLogger(__name__)
SCENARIO_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


@router.post("/scenarios", response_model=ScenarioCreatedResponse, status_code=201)
async def create_scenario(
    config: ScenarioConfig,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create and persist a new scenario. Returns the scenario_id."""
    record = await repository.create_scenario(session, config)
    return {"scenario_id": str(record.id), "name": record.name}


@router.get("/scenarios", response_model=list[ScenarioSummaryResponse])
async def list_scenarios(
    session: AsyncSession = Depends(get_session),
) -> list[ScenarioSummaryResponse]:
    """List all scenarios."""
    records = await repository.list_scenarios(session)
    return [
        {"scenario_id": str(r.id), "name": r.name, "created_at": r.created_at.isoformat()}
        for r in records
    ]


@router.get("/scenarios/templates", response_model=list[ScenarioTemplateResponse])
async def list_scenario_templates() -> list[ScenarioTemplateResponse]:
    """Return validated scenario configurations shipped with the backend."""
    templates: list[ScenarioTemplateResponse] = []
    for path in sorted(SCENARIO_TEMPLATE_DIR.glob("*.yaml")):
        try:
            config = ScenarioConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            logger.exception("Unable to load scenario template %s", path.name)
            raise HTTPException(
                status_code=500,
                detail=f"Scenario template {path.name} is invalid or unreadable",
            ) from exc
        templates.append(
            ScenarioTemplateResponse(
                template_id=path.stem,
                name=config.name,
                description=config.description,
                config=config,
            )
        )
    return templates


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetailsResponse)
async def get_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieve a scenario config by ID."""
    record = await repository.get_scenario(session, scenario_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"scenario_id": str(record.id), "name": record.name, "config": record.config_json}
