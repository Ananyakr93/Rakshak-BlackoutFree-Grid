"""
REST endpoints for simulation run management.

  POST   /api/v1/runs               — start a simulation run
  GET    /api/v1/runs               — list all runs
  GET    /api/v1/runs/{run_id}      — get run status and current state
  POST   /api/v1/runs/{run_id}/stop — request controlled stop
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel.ext.asyncio.session import AsyncSession

from app.control.restoration_policy import StaggeredRestorationPolicy
from app.control.shedding_policy import ADMSFeederPolicy, PriorityEdgePolicy, UnmanagedPolicy
from app.core.config import settings
from app.core.run_manager import RunEntry, run_manager
from app.db import repository
from app.db.session import get_session
from app.hil.adapter import HILAdapter, PySerialLineTransport
from app.schemas.api import (
    BuildingSnapshotResponse,
    FeederEstimateResponse,
    PolicyName,
    RestorationStatusResponse,
    RunAgentResponse,
    RunHistoryResponse,
    RunIntegrationsResponse,
    RunSnapshotResponse,
)
from app.schemas.events import ApplianceStateUpdate, ControlEvent
from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample
from app.twin.building_twin import BuildingTwin
from app.twin.disturbances import make_disturbance
from app.twin.feeder_estimator import (
    ASSUMED_POWER_FACTOR,
    NOMINAL_LINE_VOLTAGE_V,
    estimate_feeder_branches,
)
from app.twin.grid_model import GridModel
from app.twin.simulation_clock import SimulationClock

router = APIRouter(tags=["runs"])
logger = logging.getLogger(__name__)

class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: uuid.UUID
    policy: PolicyName
    seed: int | None = Field(default=None, ge=0)
    hil_port: str | None = None
    hil_building_id: str | None = None
    hil_baud_rate: int = Field(default=115200, gt=0)
    playback_speed: float = Field(default=30.0, ge=1.0, le=120.0)

    @model_validator(mode="after")
    def validate_hil_target(self) -> StartRunRequest:
        if (self.hil_port is None) != (self.hil_building_id is None):
            raise ValueError("hil_port and hil_building_id must be provided together")
        if self.hil_port is not None and not self.hil_port.strip():
            raise ValueError("hil_port must not be empty")
        if self.hil_building_id is not None and self.policy not in {
            "P2_priority_edge",
            "P2_priority_edge_synchronized",
        }:
            raise ValueError("HIL control requires the P2 priority-edge policy")
        return self


class RunStartResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["pending"]
    policy: PolicyName


class RunControlResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["running", "paused"]


class PlaybackSpeedResponse(BaseModel):
    run_id: uuid.UUID
    playback_speed: float


class StopRunResponse(BaseModel):
    run_id: uuid.UUID
    message: str


def _make_policy(
    policy_name: str,
    run_id: uuid.UUID,
    building_ids: list[str],
    scenario: ScenarioConfig,
):
    if policy_name == "P0_unmanaged":
        return UnmanagedPolicy(run_id=run_id)
    if policy_name == "P1_adms_feeder":
        groups = scenario.emulated_feeder_stages or {"stage1": building_ids}
        return ADMSFeederPolicy(
            feeder_groups=groups,
            run_id=run_id,
            grid_params=scenario.grid_params,
            sample_interval_s=settings.AGENT_SAMPLE_INTERVAL_S,
        )
    if policy_name in {"P2_priority_edge", "P2_priority_edge_synchronized"}:
        grid = scenario.grid_params
        area_base_kw = max(
            sum(
                appliance.rated_power_kw * building.weight_k
                for building in scenario.buildings
                for appliance in building.appliances
            ),
            1.0,
        )
        return PriorityEdgePolicy(
            run_id=run_id,
            restoration_policy=StaggeredRestorationPolicy(
                run_id=run_id,
                t_stable_s=grid.t_stable_s,
                f_recovery_hz=grid.f_recovery_hz,
                f_freeze_hz=grid.f_s1_hz,
                H=grid.H,
                area_base_kw=area_base_kw,
                sample_interval_s=settings.AGENT_SAMPLE_INTERVAL_S,
                stagger_enabled=policy_name == "P2_priority_edge",
            ),
            grid_params=grid,
            sample_interval_s=settings.AGENT_SAMPLE_INTERVAL_S,
            policy_name=policy_name,
        )
    if policy_name == "P3_priority_edge_no_restoration":
        return PriorityEdgePolicy(
            run_id=run_id,
            policy_name=policy_name,
            enable_restoration=False,
            grid_params=scenario.grid_params,
            sample_interval_s=settings.AGENT_SAMPLE_INTERVAL_S,
        )
    raise ValueError(f"Unknown policy: {policy_name!r}")


async def _run_simulation(
    run_id: uuid.UUID,
    scenario: ScenarioConfig,
    policy_name: str,
    seed: int,
    db_url: str,
    hil_port: str | None = None,
    hil_building_id: str | None = None,
    hil_baud_rate: int = 115200,
    playback_speed: float = 30.0,
) -> None:
    """Background task: runs the simulation and persists results."""
    from app.db.session import AsyncSessionFactory

    entry = run_manager.get(run_id)
    if entry is None:
        return

    hil_adapter: HILAdapter | None = None
    telemetry_batch: list[TelemetrySample] = []
    event_batch: list[ControlEvent] = []
    try:
        async with AsyncSessionFactory() as session:
            await repository.update_run_status(session, run_id, "running")
            run_manager.set_status(run_id, "running")

        buildings = [BuildingTwin.from_config(bc) for bc in scenario.buildings]
        if hil_port is not None and hil_building_id is not None:
            target = next(
                (building for building in buildings if building.building_id == hil_building_id),
                None,
            )
            if target is None:
                raise ValueError(f"HIL building {hil_building_id!r} is not in the scenario")
            if not target.appliances:
                raise ValueError("HIL building must contain at least one configured appliance")
            hil_adapter = HILAdapter(
                PySerialLineTransport(hil_port, baud_rate=hil_baud_rate),
                hil_building_id,
                {appliance.appliance_id for appliance in target.appliances},
            )
        grid = GridModel(scenario.grid_params, mode=scenario.area_mode)
        disturbance = make_disturbance(scenario.disturbance, seed=seed)
        policy = _make_policy(
            policy_name,
            run_id,
            [b.building_id for b in buildings],
            scenario,
        )

        BATCH_SIZE = 500

        async def telemetry_sink(sample: TelemetrySample) -> None:
            telemetry_batch.append(sample)
            await run_manager.push_telemetry(run_id, sample)
            if len(telemetry_batch) >= BATCH_SIZE:
                async with AsyncSessionFactory() as session:
                    await repository.save_telemetry_batch(session, list(telemetry_batch))
                telemetry_batch.clear()

        async def event_sink(event: ControlEvent) -> None:
            event_batch.append(event)
            run_manager.push_event(run_id, event)

        async def building_state_sink(update: ApplianceStateUpdate) -> None:
            run_manager.push_building_update(run_id, update)

        clock = SimulationClock(
            scenario=scenario,
            run_id=run_id,
            grid=grid,
            disturbance=disturbance,
            buildings=buildings,
            policy=policy,
            telemetry_sink=telemetry_sink,
            event_sink=event_sink,
            building_state_sink=building_state_sink,
            hil_adapter=hil_adapter,
            playback_speed=playback_speed,
        )
        entry.clock = clock

        result = await clock.run()

        # Flush remaining telemetry
        if telemetry_batch:
            async with AsyncSessionFactory() as session:
                await repository.save_telemetry_batch(session, telemetry_batch)
            telemetry_batch.clear()

        # Save events in one transaction.
        if event_batch:
            async with AsyncSessionFactory() as session:
                await repository.save_control_events_batch(session, event_batch)
            event_batch.clear()

        # Compute and save metrics
        from app.evaluation.metrics import compute_all_metrics

        final_telemetry = (
            run_manager.get(run_id).telemetry_buffer if run_manager.get(run_id) else []
        )
        metrics = compute_all_metrics(result, scenario, final_telemetry)
        metric_units = {
            "frequency_nadir_hz": "Hz",
            "max_rocof_hz_per_s": "Hz/s",
            "recovery_time_s": "s",
            "critical_ens_kwh": "kWh",
            "medical_load_interruption_s": "device-s",
            "feeder_trips_count": "events",
            "rebound_peak_pu": "pu",
            "energy_curtailed_critical_kwh": "kWh",
            "energy_curtailed_essential_kwh": "kWh",
            "energy_curtailed_deferrable_kwh": "kWh",
            "jains_fairness_index": "index",
            "over_frequency_excursion_time_s": "s",
            "total_shed_events": "events",
            "total_restore_events": "events",
        }
        metric_dict = {
            name: (value, metric_units.get(name, ""))
            for name, value in metrics.items()
        }
        async with AsyncSessionFactory() as session:
            await repository.save_metrics(session, run_id, metric_dict)
            await repository.update_run_status(
                session, run_id, "completed", completed_at=datetime.now(tz=timezone.utc)
            )
        run_manager.set_status(run_id, "completed")
    except Exception:
        run_manager.set_status(run_id, "failed")
        try:
            async with AsyncSessionFactory() as session:
                if telemetry_batch:
                    await repository.save_telemetry_batch(session, telemetry_batch)
                    telemetry_batch.clear()
                if event_batch:
                    await repository.save_control_events_batch(session, event_batch)
                    event_batch.clear()
                await repository.update_run_status(
                    session,
                    run_id,
                    "failed",
                    completed_at=datetime.now(tz=timezone.utc),
                )
        except Exception:
            logger.exception("Could not persist failure state for run %s", run_id)
        raise
    finally:
        if hil_adapter is not None:
            await hil_adapter.close()


@router.post("/runs", response_model=RunStartResponse, status_code=202)
async def start_run(
    request: StartRunRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Start a new simulation run as a background task."""
    # Fetch scenario
    scenario_record = await repository.get_scenario(session, request.scenario_id)
    if scenario_record is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    import json as _json

    scenario = ScenarioConfig(**_json.loads(scenario_record.config_json))
    if request.hil_building_id is not None and request.hil_building_id not in {
        building.building_id for building in scenario.buildings
    }:
        raise HTTPException(status_code=422, detail="HIL building is not part of the scenario")
    if request.hil_building_id is not None and not next(
        building
        for building in scenario.buildings
        if building.building_id == request.hil_building_id
    ).appliances:
        raise HTTPException(status_code=422, detail="HIL building has no configured appliances")
    seed = request.seed if request.seed is not None else scenario.seed
    scenario = scenario.model_copy(update={"seed": seed})

    # Create DB run record
    run_record = await repository.create_run(
        session, request.scenario_id, request.policy, seed, scenario
    )
    run_id = run_record.id

    # Register in run manager
    entry = run_manager.register(run_id, request.policy, len(scenario.buildings))
    entry.playback_speed = request.playback_speed
    entry.hil_building_id = request.hil_building_id

    # Launch background task
    from app.core.config import settings

    background_tasks.add_task(
        _run_simulation,
        run_id,
        scenario,
        request.policy,
        seed,
        settings.DATABASE_URL,
        request.hil_port,
        request.hil_building_id,
        request.hil_baud_rate,
        request.playback_speed,
    )

    return {"run_id": str(run_id), "status": "pending", "policy": request.policy}


@router.get("/runs", response_model=list[RunHistoryResponse])
async def list_runs(
    session: AsyncSession = Depends(get_session),
) -> list[RunHistoryResponse]:
    """List all simulation runs."""
    records = await repository.list_runs(session)
    return [
        {
            "run_id": str(r.id),
            "scenario_id": str(r.scenario_id),
            "scenario_name": json.loads(r.config_snapshot_json).get("name", "Unknown scenario"),
            "policy": r.policy,
            "seed": r.seed,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
        }
        for r in records
    ]


@router.get("/runs/{run_id}", response_model=RunSnapshotResponse)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get run status and current simulation state."""
    record = await repository.get_run(session, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    state = run_manager.get_run_state(run_id)
    return {
        "run_id": str(run_id),
        "status": state.status if state else record.status,
        "playback_speed": state.playback_speed if state else None,
        "is_paused": state.is_paused if state else False,
        "current_time_s": state.current_time_s if state else 0.0,
        "active_buildings": state.active_buildings if state else 0,
        "latest_frequency_hz": state.latest_sample.frequency_hz
        if state and state.latest_sample
        else None,
        "scenario_id": str(record.scenario_id),
        "scenario": json.loads(record.config_snapshot_json),
        "policy": record.policy,
        "seed": record.seed,
    }


class PlaybackSpeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    playback_speed: float = Field(..., ge=1.0, le=120.0)


def _active_run_clock(run_id: uuid.UUID) -> RunEntry:
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None or entry.status not in {"running", "paused"}:
        raise HTTPException(status_code=409, detail="Run is not active")
    return entry


@router.post("/runs/{run_id}/pause", response_model=RunControlResponse)
async def pause_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pause an active simulation without terminating it."""
    entry = _active_run_clock(run_id)
    was_paused = entry.clock.is_paused()
    entry.clock.pause()
    try:
        await repository.update_run_status(session, run_id, "paused")
    except Exception:
        if not was_paused:
            entry.clock.resume()
        raise
    run_manager.set_status(run_id, "paused")
    return {"run_id": str(run_id), "status": "paused"}


@router.post("/runs/{run_id}/resume", response_model=RunControlResponse)
async def resume_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resume a paused simulation."""
    entry = _active_run_clock(run_id)
    await repository.update_run_status(session, run_id, "running")
    entry.clock.resume()
    run_manager.set_status(run_id, "running")
    return {"run_id": str(run_id), "status": "running"}


@router.post("/runs/{run_id}/speed", response_model=PlaybackSpeedResponse)
async def set_run_speed(run_id: uuid.UUID, request: PlaybackSpeedRequest) -> dict:
    """Change simulated seconds per wall-clock second for an active run."""
    entry = _active_run_clock(run_id)
    entry.clock.set_playback_speed(request.playback_speed)
    entry.playback_speed = request.playback_speed
    return {"run_id": str(run_id), "playback_speed": entry.playback_speed}


@router.get("/runs/{run_id}/integrations", response_model=RunIntegrationsResponse)
async def get_run_integrations(run_id: uuid.UUID) -> dict:
    """Report optional HIL and model-derived NILM integration state."""
    entry = run_manager.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run state is not available in this process")
    adapter = entry.clock.hil_adapter if entry.clock is not None else None
    health = adapter.health() if adapter is not None else None
    return {
        "hil": {
            "status": (
                "connected" if health and health.connected
                else "waiting_for_heartbeat" if adapter is not None
                else "not_configured"
            ),
            "building_id": entry.hil_building_id,
            "fallback_active": health.fallback_active if health else False,
            "received_messages": health.received_messages if health else 0,
            "transmitted_messages": health.transmitted_messages if health else 0,
            "last_feedback_latency_ms": (
                health.last_feedback_latency_ms if health else None
            ),
            "heartbeat_age_s": health.heartbeat_age_s if health else None,
            "controller_status": health.controller_status if health else None,
            "acknowledged_appliance_states": (
                health.acknowledged_appliance_states if health else {}
            ),
            "last_feedback_sequence": (
                health.last_feedback_sequence if health else None
            ),
        },
        "nilm": {
            "status": "simulated_estimates" if entry.clock is not None else "unavailable",
            "source": "simulated_aggregate_load",
        },
    }


@router.get("/runs/{run_id}/agents", response_model=list[RunAgentResponse])
async def get_run_agents(run_id: uuid.UUID) -> list[dict]:
    """Return live per-building virtual edge-agent decisions and link status."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(status_code=404, detail="Agent state is not available in this process")
    return entry.clock.agent_status()


@router.get("/runs/{run_id}/restoration", response_model=RestorationStatusResponse)
async def get_run_restoration(run_id: uuid.UUID) -> dict:
    """Return the restoration queue and its live frequency safety gates."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(
            status_code=404,
            detail="Restoration state is not available in this process",
        )
    return entry.clock.restoration_status()


@router.get("/runs/{run_id}/feeder", response_model=FeederEstimateResponse)
async def get_run_feeder(run_id: uuid.UUID) -> dict:
    """Return estimated current for model branches at nominal voltage and power factor."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(
            status_code=404,
            detail="Feeder estimates are not available in this process",
        )
    branches = estimate_feeder_branches(entry.clock.buildings)
    return {
        "source": "simulated_load_estimate",
        "nominal_line_voltage_v": NOMINAL_LINE_VOLTAGE_V,
        "assumed_power_factor": ASSUMED_POWER_FACTOR,
        "total_active_power_kw": sum(branch.active_power_kw for branch in branches),
        "branches": [
            {
                "building_id": branch.building_id,
                "active_power_kw": branch.active_power_kw,
                "estimated_current_a": branch.estimated_current_a,
            }
            for branch in branches
        ],
    }


@router.get("/runs/{run_id}/buildings", response_model=list[BuildingSnapshotResponse])
async def get_run_buildings(run_id: uuid.UUID) -> list[dict]:
    """Return current appliance states from the in-memory simulation twin."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(status_code=404, detail="Run state is not available in this process")

    return [
        BuildingSnapshotResponse.model_validate(snapshot).model_dump(mode="json")
        for snapshot in entry.clock.building_snapshots()
    ]


@router.post("/runs/{run_id}/stop", response_model=StopRunResponse)
async def stop_run(run_id: uuid.UUID) -> dict:
    """Request a graceful stop of an active run."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(status_code=404, detail="Run not found or not active")
    entry.clock.stop()
    return {"run_id": str(run_id), "message": "stop requested"}
