"""
REST endpoints for simulation metrics and results.

  GET /api/v1/runs/{run_id}/metrics   — retrieve computed metrics
  GET /api/v1/runs/{run_id}/events    — retrieve control events (filterable)
  GET /api/v1/runs/{run_id}/telemetry — retrieve telemetry (downsample support)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.runs import _make_policy
from app.core.config import settings
from app.core.run_manager import run_manager
from app.db import repository
from app.db.session import get_session
from app.evaluation.experiments import ExperimentRunner
from app.schemas.api import (
    LiveComparisonResponse,
    NILMEstimateResponse,
    NILMEvaluationResponse,
    NILMSignalResponse,
    RunEventResponse,
    RunMetricResponse,
    RunTelemetryResponse,
    SavedBaselineResponse,
)
from app.schemas.scenario import ScenarioConfig

router = APIRouter(tags=["metrics"])


class LiveComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioConfig
    n_seeds: int = Field(default=3, ge=2, le=10)


@router.get("/runs/{run_id}/metrics", response_model=list[RunMetricResponse])
async def get_metrics(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[RunMetricResponse]:
    """Return all metrics for a completed run."""
    records = await repository.get_run_metrics(session, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="No metrics found for this run")
    return [
        {
            "metric_name": r.metric_name,
            "metric_value": r.metric_value,
            "unit": r.unit,
            "notes": r.notes,
        }
        for r in records
    ]


@router.get("/runs/{run_id}/nilm", response_model=list[NILMEstimateResponse])
async def get_nilm_estimates(run_id: uuid.UUID) -> list[NILMEstimateResponse]:
    """Return separate NILM estimates derived from simulated aggregate load."""
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(
            status_code=404,
            detail="NILM estimates are not available in this process",
        )
    return entry.clock.nilm_events()


@router.get("/runs/{run_id}/nilm/signal", response_model=list[NILMSignalResponse])
async def get_nilm_signal(
    run_id: uuid.UUID,
    building_id: str | None = Query(default=None),
) -> list[NILMSignalResponse]:
    """Return bounded synthetic aggregate samples and twin-derived transitions."""
    samples = _get_nilm_signal_samples(run_id)
    return [
        sample for sample in samples
        if building_id is None or sample["building_id"] == building_id
    ]


def _get_nilm_signal_samples(run_id: uuid.UUID) -> list[dict]:
    entry = run_manager.get(run_id)
    if entry is None or entry.clock is None:
        raise HTTPException(
            status_code=404,
            detail="NILM signal is not available in this process",
        )
    return entry.clock.nilm_signal()


@router.get("/runs/{run_id}/nilm/evaluation", response_model=NILMEvaluationResponse)
async def get_nilm_evaluation(run_id: uuid.UUID) -> NILMEvaluationResponse:
    """Compare detected load steps with simulated appliance state transitions."""
    samples = _get_nilm_signal_samples(run_id)
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for sample in samples:
        actual = list(sample["ground_truth_changes"])
        predicted = list(sample["estimated_changes"])
        used_predictions: set[int] = set()
        for change in actual:
            match_index = next(
                (
                    index
                    for index, estimate in enumerate(predicted)
                    if index not in used_predictions
                    and estimate.get("appliance_type") == change.get("appliance_type")
                    and estimate.get("event_type") == change.get("event_type")
                ),
                None,
            )
            if match_index is None:
                false_negative += 1
            else:
                used_predictions.add(match_index)
                true_positive += 1
        false_positive += len(predicted) - len(used_predictions)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    return {
        "source": "simulated_aggregate_load_vs_twin_state",
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1_score": (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        ),
    }


@router.post("/experiments/compare", response_model=LiveComparisonResponse)
async def compare_four_control_modes(
    request: LiveComparisonRequest,
) -> LiveComparisonResponse:
    """Run a paired four-mode comparison over the requested deterministic seeds."""
    scenario = request.scenario
    building_ids = [building.building_id for building in scenario.buildings]
    policy_names = [
        "P0_unmanaged",
        "P1_adms_feeder",
        "P2_priority_edge",
        "P2_priority_edge_synchronized",
    ]
    policies = [
        _make_policy(policy_name, uuid.uuid4(), building_ids, scenario)
        for policy_name in policy_names
    ]
    experiment = await ExperimentRunner().run_experiment(
        scenario,
        policies,
        n_seeds=request.n_seeds,
    )
    trajectories = {
        policy: [
            sample.model_dump(mode="json")
            for sample in runs[0].telemetry
        ]
        for policy, runs in experiment.policy_results.items()
        if runs
    }
    return {
        "scenario_name": experiment.scenario_name,
        "base_seed": scenario.seed,
        "n_seeds": request.n_seeds,
        "seed_range": [scenario.seed, scenario.seed + request.n_seeds - 1],
        "source": "paired_simulation",
        "summary": {
            policy: {
                "policy_name": summary.policy_name,
                "n_seeds": summary.n_seeds,
                "mean_nadir_hz": summary.mean_nadir_hz,
                "mean_max_rocof_hz_per_s": summary.mean_max_rocof_hz_per_s,
                "std_nadir_hz": summary.std_nadir_hz,
                "ci95_nadir": list(summary.ci95_nadir),
                "mean_recovery_time_s": summary.mean_recovery_time_s,
                "mean_critical_ens_kwh": summary.mean_critical_ens_kwh,
                "mean_medical_load_interruption_s": (
                    summary.mean_medical_load_interruption_s
                ),
                "mean_feeder_trips": summary.mean_feeder_trips,
                "mean_rebound_peak_pu": summary.mean_rebound_peak_pu,
                "mean_jains_index": summary.mean_jains_index,
                "raw_metrics": summary.raw_metrics,
            }
            for policy, summary in experiment.summary.items()
        },
        "frequency_trajectories": trajectories,
    }


@router.get("/runs/{run_id}/events", response_model=list[RunEventResponse])
async def get_events(
    run_id: uuid.UUID,
    event_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[RunEventResponse]:
    """Return control events, optionally filtered by event_type."""
    entry = run_manager.get(run_id)
    if entry is not None:
        records = [
            event for event in entry.event_buffer
            if event_type is None or event.event_type == event_type
        ]
    else:
        records = await repository.get_control_events(session, run_id, event_type=event_type)
    return [
        {
            "event_id": str(getattr(r, "event_id", getattr(r, "id", ""))),
            "simulation_time_s": r.simulation_time_s,
            "event_type": r.event_type,
            "building_id": r.building_id,
            "appliance_id": r.appliance_id,
            "reason": r.reason,
            "frequency_hz": r.frequency_hz,
            "priority": r.priority,
        }
        for r in records
    ]


@router.get("/runs/{run_id}/telemetry", response_model=list[RunTelemetryResponse])
async def get_telemetry(
    run_id: uuid.UUID,
    downsample: int = Query(default=1, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[RunTelemetryResponse]:
    """Return telemetry records, optionally downsampled (every Nth sample)."""
    entry = run_manager.get(run_id)
    if entry is not None:
        records = entry.telemetry_buffer[::downsample]
    else:
        records = await repository.get_telemetry(session, run_id, downsample=downsample)
    return [
        {
            "simulation_time_s": r.simulation_time_s,
            "frequency_hz": r.frequency_hz,
            "generation_pu": r.generation_pu,
            "demand_pu": r.demand_pu,
            "generation_disturbance_pu": r.generation_disturbance_pu,
            "demand_disturbance_pu": r.demand_disturbance_pu,
            "frequency_stage": r.frequency_stage,
            "rocof_hz_per_s": r.rocof_hz_per_s,
            "sequence_number": r.sequence_number,
        }
        for r in records
    ]


@router.get("/experiments/baseline", response_model=SavedBaselineResponse)
async def get_saved_baseline_results() -> SavedBaselineResponse:
    """Return the committed E1-E4 experiment summary for offline demonstrations."""
    path = (
        Path(settings.EXPERIMENT_RESULTS_PATH)
        if settings.EXPERIMENT_RESULTS_PATH
        else Path(__file__).resolve().parents[3]
        / "experiments"
        / "baseline"
        / "results_e1_e4.json"
    )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Saved baseline experiment results are unavailable",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Saved baseline experiment results could not be read",
        ) from exc
