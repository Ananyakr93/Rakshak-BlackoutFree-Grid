"""
Pydantic v2 schemas for simulation telemetry and run state.

TelemetrySample: one time-series record pushed via WebSocket and stored in DB.
RunState: current snapshot of a run returned by the GET /runs/{id} endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TelemetrySample(BaseModel):
    """One telemetry snapshot from the simulation clock."""

    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    simulation_time_s: float
    wall_clock_ts: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    frequency_hz: float
    generation_pu: float
    demand_pu: float
    generation_disturbance_pu: float = 0.0
    demand_disturbance_pu: float = 0.0
    frequency_stage: str
    rocof_hz_per_s: float
    sequence_number: int
    schema_version: str = "1.0"


class RunState(BaseModel):
    """Current state of a simulation run, returned by GET /runs/{run_id}."""

    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    status: Literal["pending", "running", "paused", "completed", "failed"]
    current_time_s: float
    latest_sample: TelemetrySample | None = None
    active_buildings: int
    playback_speed: float
    is_paused: bool
