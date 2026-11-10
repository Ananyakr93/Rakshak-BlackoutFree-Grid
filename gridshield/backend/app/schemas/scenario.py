"""
Pydantic v2 schemas for scenario configuration.

Defines the full scenario config hierarchy:
  ScenarioConfig -> DisturbanceConfig, GridParams, list[BuildingConfig]
  BuildingConfig -> list[ApplianceConfig]
  FaultConfig    -> communication fault injection parameters

These are API/validation shapes, NOT SQLModel table models.
All fields use unit suffixes (_s, _hz, _kw, _pu) where ambiguous.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApplianceConfig(BaseModel):
    """Configuration for a single virtual appliance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    appliance_id: str
    appliance_type: str
    priority: Literal["critical", "essential", "deferrable"]
    rated_power_kw: float = Field(..., gt=0, description="Rated power in kilowatts")
    min_on_time_s: float = Field(default=0.0, ge=0)
    min_off_time_s: float = Field(default=0.0, ge=0)
    max_shed_minutes: float | None = Field(default=None, gt=0)
    enrolled: bool = True
    initial_state: Literal["ON", "OFF"] = "ON"
    compressor_lockout_s: float | None = Field(default=None, ge=0)
    inrush_multiplier: float | None = Field(default=None, ge=1)
    inrush_duration_s: float | None = Field(default=None, ge=0)
    startup_recovery_profile: Literal["linear", "exponential"] = "linear"


class BuildingConfig(BaseModel):
    """Configuration for a virtual building and its appliances."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    building_id: str
    weight_k: int = Field(default=1, ge=1, description="Real buildings this twin represents")
    appliances: list[ApplianceConfig]


class DisturbanceConfig(BaseModel):
    """Configuration for the power disturbance event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[
        "generation_loss",
        "demand_surge",
        "combined",
        "solar_surplus",
        "solar_cloud_drop",
    ]
    start_time_s: float = Field(..., ge=0)
    magnitude_pu: float = Field(..., gt=0, le=1, description="Per-unit disturbance magnitude")
    duration_s: float = Field(..., gt=0)
    recovery_ramp_s: float = Field(default=30.0, ge=0)
    solar_share_pu: float | None = Field(
        default=None,
        gt=0,
        le=1,
        description="Solar share of area base generation; required for solar_cloud_drop",
    )

    @model_validator(mode="after")
    def validate_solar_cloud_drop(self) -> DisturbanceConfig:
        if self.type == "solar_cloud_drop" and self.solar_share_pu is None:
            raise ValueError("solar_cloud_drop requires solar_share_pu")
        return self


class FaultConfig(BaseModel):
    """Communication fault injection parameters for the in-process bus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    delay_range_s: tuple[float, float] = Field(
        default=(0.0, 0.0),
        description="Min and max uniform random delivery delay (seconds)",
    )
    loss_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    duplicate_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    out_of_order: bool = False
    shuffle_window_size: int = Field(default=5, ge=2)

    @model_validator(mode="after")
    def validate_delay_range(self) -> FaultConfig:
        lo, hi = self.delay_range_s
        if lo < 0 or hi < lo:
            raise ValueError("delay_range_s must be (lo, hi) with 0 <= lo <= hi")
        return self


class GridParams(BaseModel):
    """
    Grid model parameters.

    All threshold defaults are per framework.md §6.3 and IEGC 2023.
    Human verification is required before citing these as certified
    KPTCL/SLDC settings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Core swing/governor parameters (framework.md §7)
    f0_hz: float = Field(default=50.0, description="Nominal frequency (Hz)")
    H: float = Field(default=4.0, gt=0, description="Inertia constant (seconds)")
    D: float = Field(default=1.5, gt=0, description="Load damping coefficient (pu)")
    R: float = Field(default=0.05, gt=0, description="Governor droop (pu, e.g. 0.05 = 5%)")
    deadband_hz: float = Field(default=0.03, ge=0, description="Governor deadband (Hz)")
    Tg: float = Field(default=0.1, gt=0, description="Governor time constant (s)")
    Tt: float = Field(default=0.4, gt=0, description="Turbine time constant (s)")
    up_reserve_pu: float = Field(
        default=0.20, gt=0, description="Max upward generation reserve (pu)"
    )
    down_reserve_pu: float = Field(default=0.10, gt=0, description="Max downward reserve (pu)")
    dt_s: float = Field(default=0.02, gt=0, description="RK4 integration step (s)")

    # Stage thresholds (framework.md §6.3)
    f_s0_hz: float = Field(default=49.90, description="S0 Advisory trigger (Hz)")
    f_s1_hz: float = Field(default=49.85, description="S1 shed deferrable trigger (Hz)")
    f_s2_hz: float = Field(default=49.60, description="S2 shed essential trigger (Hz)")
    f_s3_hz: float = Field(default=49.40, description="S3 shed remaining essential trigger (Hz)")
    f_o1_hz: float = Field(default=50.05, description="O1 absorb trigger (Hz)")
    f_o2_hz: float = Field(default=50.20, description="O2 absorb+ trigger (Hz)")
    rocof_s2_threshold: float = Field(
        default=-0.3, description="RoCoF threshold triggering S2 (Hz/s)"
    )

    # Recovery / restoration thresholds (framework.md §6.4)
    f_recovery_hz: float = Field(default=49.95, description="Recovery band lower bound (Hz)")
    t_stable_s: float = Field(
        default=60.0, gt=0, description="Stability hold before restoration (s)"
    )

    # Stage hold durations before action
    t_s0_hold_s: float = Field(
        default=10.0, ge=0, description="S0: seconds below f_s0 before action"
    )
    t_s1_hold_s: float = Field(
        default=5.0, ge=0, description="S1: seconds below f_s1 before action"
    )
    t_s2_hold_s: float = Field(
        default=2.0, ge=0, description="S2: seconds below f_s2 before action"
    )
    t_s3_hold_s: float = Field(
        default=0.0, ge=0, description="S3: seconds below f_s3 before action"
    )
    t_p1_recovery_s: float = Field(
        default=120.0, ge=0, description="P1 recovery hold above the recovery threshold"
    )
    t_o1_hold_s: float = Field(
        default=30.0, ge=0, description="O1: seconds above f_o1 before absorb"
    )


class ScenarioConfig(BaseModel):
    """
    Top-level scenario configuration.

    A scenario completely defines a simulation run: grid parameters,
    disturbance profile, buildings, and seed. Storing this alongside
    the run ensures full reproducibility from the DB record alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    description: str = ""
    seed: int = Field(..., ge=0, description="Random seed for reproducibility")
    simulation_duration_s: float = Field(..., gt=0)
    area_mode: Literal["scaled", "islanded"] = "scaled"
    edge_mode: Literal[
        "CENTRALIZED",
        "DISTRIBUTED",
        "COMMUNICATION_DEGRADED",
        "ISLANDED_AUTONOMOUS",
    ] = "DISTRIBUTED"
    emulated_feeder_stages: dict[
        Literal["stage1", "stage2", "stage3"], list[str]
    ] = Field(default_factory=dict)

    disturbance: DisturbanceConfig
    grid_params: GridParams = Field(default_factory=GridParams)
    buildings: list[BuildingConfig]
    fault_config: FaultConfig = Field(default_factory=FaultConfig)

    @field_validator("buildings")
    @classmethod
    def at_least_one_building(cls, v: list[BuildingConfig]) -> list[BuildingConfig]:
        if len(v) == 0:
            raise ValueError("At least one building is required")
        return v

    @model_validator(mode="after")
    def validate_feeder_membership_and_live_faults(self) -> ScenarioConfig:
        building_ids = {building.building_id for building in self.buildings}
        assigned_ids = [
            building_id
            for members in self.emulated_feeder_stages.values()
            for building_id in members
        ]
        if len(assigned_ids) != len(set(assigned_ids)):
            raise ValueError("A building may belong to only one emulated feeder stage")
        unknown_ids = set(assigned_ids) - building_ids
        if unknown_ids:
            raise ValueError(f"Unknown buildings in emulated feeder stages: {sorted(unknown_ids)}")
        fault = self.fault_config
        if (
            fault.delay_range_s != (0.0, 0.0)
            or fault.duplicate_probability != 0.0
            or fault.out_of_order
        ):
            raise ValueError(
                "Active simulation supports packet loss only; delay, duplication, "
                "and reordering are not wired into run execution."
            )
        return self
