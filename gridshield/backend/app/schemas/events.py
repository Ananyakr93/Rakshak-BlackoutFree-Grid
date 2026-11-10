"""
Pydantic v2 schema for control events emitted by edge agents and policies.

ControlEvent records every shed, restore, feeder trip, and no-op decision
with full context: simulation time, building/appliance, frequency at trigger,
reason string, and priority tier.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ControlEvent(BaseModel):
    """A single control decision recorded by an edge agent or policy."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    run_id: uuid.UUID
    simulation_time_s: float
    wall_clock_ts: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    event_type: str = Field(..., min_length=1, description="e.g. shed_deferrable, restore, feeder_trip, no_op")
    building_id: str
    appliance_id: str | None = None
    reason: str = Field(..., min_length=1, description="Human-readable decision reason")
    frequency_hz: float
    priority: str | None = None
    power_delta_kw: float | None = Field(
        default=None,
        ge=0,
        description="Nominal load-change magnitude in kW when reported by the model",
    )
    schema_version: str = "1.0"


class ApplianceStateUpdate(BaseModel):
    """A sequenced appliance state transition for live building views."""

    model_config = ConfigDict(frozen=True)

    type: Literal["building_state_update"] = "building_state_update"
    schema_version: Literal["1.0"] = "1.0"
    run_id: uuid.UUID
    building_id: str
    appliance_id: str
    appliance_type: str
    priority: Literal["critical", "essential", "deferrable"]
    previous_state: Literal[
        "ON", "RUNNING", "OFF", "SHED", "WAITING_RESTORATION", "LOCKED_OUT", "UNAVAILABLE"
    ]
    current_state: Literal[
        "ON", "RUNNING", "OFF", "SHED", "WAITING_RESTORATION", "LOCKED_OUT", "UNAVAILABLE"
    ]
    current_power_kw: float = Field(..., ge=0)
    rated_power_kw: float = Field(..., gt=0)
    simulation_time_s: float = Field(..., ge=0)
    sequence_number: int = Field(..., ge=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
