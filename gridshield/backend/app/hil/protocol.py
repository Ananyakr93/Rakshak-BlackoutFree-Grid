"""Versioned JSON-line protocol for a designated virtual-building controller."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "1.0"


class HILTelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    message_type: Literal["telemetry"] = "telemetry"
    sequence: int = Field(ge=0)
    simulation_time_s: float = Field(ge=0, allow_inf_nan=False)
    building_id: str = Field(min_length=1)
    frequency_hz: float = Field(allow_inf_nan=False)
    rocof_hz_per_s: float = Field(allow_inf_nan=False)
    appliances: list[dict[str, str | float | bool]]


class HILFeedbackMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    message_type: Literal["feedback", "heartbeat"]
    sequence: int = Field(ge=0)
    building_id: str = Field(min_length=1)
    appliance_states: dict[str, Literal["ON", "OFF", "SHED", "LOCKED_OUT"]] = Field(
        default_factory=dict
    )
    shed_commands: list[str] = Field(default_factory=list)
    restore_commands: list[str] = Field(default_factory=list)
    controller_status: str = Field(default="ok", min_length=1)
