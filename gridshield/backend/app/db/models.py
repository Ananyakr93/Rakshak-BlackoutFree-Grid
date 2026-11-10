"""
SQLModel table models for GridShield persistence.

Tables: Scenario, SimulationRun, Building, ApplianceRecord,
        TelemetryRecord, ControlEventRecord, RunMetric.

Every run stores a config_snapshot_json so results are fully
reproducible from the database record alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import ClassVar

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Scenario(SQLModel, table=True):
    """Stored scenario configuration."""

    __tablename__ = "scenarios"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    description: str = ""
    seed: int
    config_json: str  # JSON-serialised ScenarioConfig
    created_at: datetime = Field(default_factory=_utcnow)


class SimulationRun(SQLModel, table=True):
    """A single simulation run under a specific policy and seed."""

    __tablename__ = "simulation_runs"
    model_config: ClassVar[dict] = {"protected_namespaces": ()}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    scenario_id: uuid.UUID = Field(foreign_key="scenarios.id")
    seed: int
    policy: str
    status: str = "pending"  # pending | running | completed | failed
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    config_snapshot_json: str  # Full ScenarioConfig snapshot at run time
    model_version: str = "1.0.0"


class Building(SQLModel, table=True):
    """Virtual building associated with a run."""

    __tablename__ = "buildings"

    id: str = Field(primary_key=True)  # building_id + "_" + run_id
    run_id: uuid.UUID = Field(foreign_key="simulation_runs.id")
    building_id: str
    weight_k: int = 1
    feeder_label: str | None = None


class ApplianceRecord(SQLModel, table=True):
    """Appliance configuration persisted at run start."""

    __tablename__ = "appliance_records"

    id: str = Field(primary_key=True)  # appliance_id + "_" + run_id
    building_id: str  # FK to buildings.id (composite key)
    run_id: uuid.UUID = Field(foreign_key="simulation_runs.id")
    appliance_type: str
    priority: str
    rated_power_kw: float
    enrolled: bool = True
    min_on_time_s: float = 0.0
    min_off_time_s: float = 0.0
    max_shed_minutes: float | None = None


class TelemetryRecord(SQLModel, table=True):
    """Time-series telemetry sample from the simulation clock."""

    __tablename__ = "telemetry_records"

    id: int | None = Field(default=None, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="simulation_runs.id")
    simulation_time_s: float
    wall_clock_ts: datetime
    frequency_hz: float
    generation_pu: float
    demand_pu: float
    generation_disturbance_pu: float = 0.0
    demand_disturbance_pu: float = 0.0
    frequency_stage: str
    rocof_hz_per_s: float
    sequence_number: int


class ControlEventRecord(SQLModel, table=True):
    """Persisted control event emitted by edge agents or policies."""

    __tablename__ = "control_event_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="simulation_runs.id")
    simulation_time_s: float
    wall_clock_ts: datetime
    event_type: str
    building_id: str
    appliance_id: str | None = None
    reason: str
    frequency_hz: float
    priority: str | None = None


class RunMetric(SQLModel, table=True):
    """A named scalar metric computed at end of a simulation run."""

    __tablename__ = "run_metrics"

    id: int | None = Field(default=None, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="simulation_runs.id")
    metric_name: str
    metric_value: float
    unit: str
    notes: str | None = None
