"""
Async repository functions for GridShield database operations.

All functions accept an async SQLModel session and return typed results.
Telemetry is written in batches for performance. No ORM magic beyond
what SQLModel provides — plain async queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import (
    ControlEventRecord,
    RunMetric,
    Scenario,
    SimulationRun,
    TelemetryRecord,
)
from app.schemas.events import ControlEvent
from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample


async def create_scenario(session: AsyncSession, config: ScenarioConfig) -> Scenario:
    """Persist a new scenario and return the DB record."""
    record = Scenario(
        id=config.scenario_id,
        name=config.name,
        description=config.description,
        seed=config.seed,
        config_json=config.model_dump_json(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> Scenario | None:
    """Retrieve a scenario by ID."""
    result = await session.exec(select(Scenario).where(Scenario.id == scenario_id))
    return result.first()


async def list_scenarios(session: AsyncSession) -> list[Scenario]:
    """Return all scenarios ordered by creation time."""
    result = await session.exec(select(Scenario).order_by(Scenario.created_at.desc()))  # type: ignore[arg-type]
    return list(result.all())


async def create_run(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    policy: str,
    seed: int,
    config_snapshot: ScenarioConfig,
) -> SimulationRun:
    """Create a new simulation run record in 'pending' status."""
    record = SimulationRun(
        scenario_id=scenario_id,
        seed=seed,
        policy=policy,
        status="pending",
        config_snapshot_json=config_snapshot.model_dump_json(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def update_run_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    completed_at: datetime | None = None,
) -> None:
    """Update the status (and optionally completed_at) of a run."""
    result = await session.exec(select(SimulationRun).where(SimulationRun.id == run_id))
    run = result.first()
    if run is None:
        return
    run.status = status
    if completed_at is not None:
        run.completed_at = completed_at
    session.add(run)
    await session.commit()


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> SimulationRun | None:
    """Retrieve a simulation run by ID."""
    result = await session.exec(select(SimulationRun).where(SimulationRun.id == run_id))
    return result.first()


async def list_runs(session: AsyncSession) -> list[SimulationRun]:
    """Return all runs ordered by start time descending."""
    result = await session.exec(
        select(SimulationRun).order_by(SimulationRun.started_at.desc())  # type: ignore[arg-type]
    )
    return list(result.all())


async def save_telemetry_batch(
    session: AsyncSession, samples: list[TelemetrySample]
) -> None:
    """Persist a batch of telemetry samples."""
    for s in samples:
        record = TelemetryRecord(
            run_id=s.run_id,
            simulation_time_s=s.simulation_time_s,
            wall_clock_ts=s.wall_clock_ts,
            frequency_hz=s.frequency_hz,
            generation_pu=s.generation_pu,
            demand_pu=s.demand_pu,
            generation_disturbance_pu=s.generation_disturbance_pu,
            demand_disturbance_pu=s.demand_disturbance_pu,
            frequency_stage=s.frequency_stage,
            rocof_hz_per_s=s.rocof_hz_per_s,
            sequence_number=s.sequence_number,
        )
        session.add(record)
    await session.commit()


async def save_control_events_batch(
    session: AsyncSession, events: list[ControlEvent]
) -> None:
    """Persist control events together in a single transaction."""
    for event in events:
        session.add(
            ControlEventRecord(
                id=event.event_id,
                run_id=event.run_id,
                simulation_time_s=event.simulation_time_s,
                wall_clock_ts=event.wall_clock_ts,
                event_type=event.event_type,
                building_id=event.building_id,
                appliance_id=event.appliance_id,
                reason=event.reason,
                frequency_hz=event.frequency_hz,
                priority=event.priority,
            )
        )
    await session.commit()


async def mark_unfinished_runs_failed(session: AsyncSession) -> int:
    """Mark runs left active by a previous process as failed during startup."""
    result = await session.exec(
        select(SimulationRun).where(
            SimulationRun.status.in_(("pending", "running", "paused"))
        )
    )
    runs = list(result.all())
    completed_at = datetime.now(tz=timezone.utc)
    for run in runs:
        run.status = "failed"
        run.completed_at = completed_at
        session.add(run)
    if runs:
        await session.commit()
    return len(runs)


async def save_metrics(
    session: AsyncSession,
    run_id: uuid.UUID,
    metrics: dict[str, tuple[float, str]],
) -> None:
    """
    Persist computed metrics for a run.

    metrics: {metric_name: (value, unit)}
    """
    for name, (value, unit) in metrics.items():
        record = RunMetric(run_id=run_id, metric_name=name, metric_value=value, unit=unit)
        session.add(record)
    await session.commit()


async def get_run_metrics(session: AsyncSession, run_id: uuid.UUID) -> list[RunMetric]:
    """Retrieve all metrics for a run."""
    result = await session.exec(select(RunMetric).where(RunMetric.run_id == run_id))
    return list(result.all())


async def get_telemetry(
    session: AsyncSession,
    run_id: uuid.UUID,
    downsample: int = 1,
) -> list[TelemetryRecord]:
    """Retrieve telemetry records, returning every Nth sample if downsample > 1."""
    result = await session.exec(
        select(TelemetryRecord)
        .where(TelemetryRecord.run_id == run_id)
        .order_by(TelemetryRecord.simulation_time_s)  # type: ignore[arg-type]
    )
    records = list(result.all())
    if downsample > 1:
        records = records[::downsample]
    return records


async def get_control_events(
    session: AsyncSession,
    run_id: uuid.UUID,
    event_type: str | None = None,
) -> list[ControlEventRecord]:
    """Retrieve control events, optionally filtered by event_type."""
    query = select(ControlEventRecord).where(ControlEventRecord.run_id == run_id)
    if event_type:
        query = query.where(ControlEventRecord.event_type == event_type)
    query = query.order_by(ControlEventRecord.simulation_time_s)  # type: ignore[arg-type]
    result = await session.exec(query)
    return list(result.all())
