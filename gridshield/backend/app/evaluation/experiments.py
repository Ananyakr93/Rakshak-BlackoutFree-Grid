"""
Experiment runner for GridShield.

ExperimentRunner executes a scenario under multiple policies and multiple
random seeds, collecting paired metrics. Results include mean, std, and
95% confidence intervals per policy per metric (framework.md §9.3).
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.control.restoration_policy import StaggeredRestorationPolicy
from app.control.shedding_policy import BasePolicy
from app.evaluation.metrics import compute_all_metrics
from app.schemas.events import ControlEvent
from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample
from app.twin.building_twin import BuildingTwin
from app.twin.disturbances import make_disturbance
from app.twin.grid_model import GridModel
from app.twin.simulation_clock import SimulationClock, SimulationResult


@dataclass
class PolicySummary:
    """Aggregated statistics for one policy across multiple seeds."""

    policy_name: str
    n_seeds: int
    mean_nadir_hz: float
    mean_max_rocof_hz_per_s: float
    std_nadir_hz: float
    ci95_nadir: tuple[float, float]
    mean_recovery_time_s: float | None
    mean_critical_ens_kwh: float
    mean_medical_load_interruption_s: float
    mean_feeder_trips: float
    mean_rebound_peak_pu: float
    mean_jains_index: float
    raw_metrics: list[dict[str, float]] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Full result of an experiment (one scenario, multiple policies, multiple seeds)."""

    experiment_id: uuid.UUID = field(default_factory=uuid.uuid4)
    scenario_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    policy_results: dict[str, list[SimulationResult]] = field(default_factory=dict)
    summary: dict[str, PolicySummary] = field(default_factory=dict)
    schema_version: str = "1.0"


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _ci95(values: list[float]) -> tuple[float, float]:
    """95% CI using t-distribution approximation (z=1.96 for large n, or t for small)."""
    if len(values) < 2:
        m = _mean(values)
        return (m, m)
    m = _mean(values)
    s = _std(values)
    n = len(values)
    # Use t=2.776 for n=5, t=2.262 for n=10, z=1.96 for large n
    t_table = {
        2: 12.706,
        3: 4.303,
        4: 3.182,
        5: 2.776,
        6: 2.571,
        7: 2.447,
        8: 2.365,
        9: 2.306,
        10: 2.262,
    }
    t = t_table.get(n, 1.96)
    margin = t * s / math.sqrt(n)
    return (m - margin, m + margin)


def _build_buildings(scenario: ScenarioConfig) -> list[BuildingTwin]:
    """Construct fresh BuildingTwin instances from scenario config."""
    return [BuildingTwin.from_config(bc) for bc in scenario.buildings]


class ExperimentRunner:
    """
    Runs the same scenario under multiple policies and multiple seeds.
    Collects and compares metrics across runs.
    """

    async def run_experiment(
        self,
        scenario_config: ScenarioConfig,
        policies: list[BasePolicy],
        n_seeds: int = 3,
        telemetry_sink: Callable[[TelemetrySample], Awaitable[None]] | None = None,
        event_sink: Callable[[ControlEvent], Awaitable[None]] | None = None,
    ) -> ExperimentResult:
        """
        Run experiment: for each seed, run all policies with identical conditions.

        Returns ExperimentResult with per-policy summaries.
        """
        result = ExperimentResult(scenario_name=scenario_config.name)

        # Generate seeds deterministically from the base seed
        rng_seeds = [scenario_config.seed + i for i in range(n_seeds)]

        for policy in policies:
            policy_name = policy.policy_name
            policy_run_results: list[SimulationResult] = []
            all_metrics: list[dict[str, float]] = []

            for _, seed in enumerate(rng_seeds):
                # Build fresh buildings for each run (must be independent)
                buildings = _build_buildings(scenario_config)

                # Rebuild scenario with this seed
                seeded_scenario = scenario_config.model_copy(update={"seed": seed})

                # Create run ID
                run_id = uuid.uuid4()

                # Wire sinks — collect telemetry in memory for metric computation
                telemetry_buffer: list[TelemetrySample] = []
                event_buffer: list[ControlEvent] = []

                async def _tel_sink(
                    s: TelemetrySample,
                    buffer: list[TelemetrySample] = telemetry_buffer,
                ) -> None:
                    buffer.append(s)
                    if telemetry_sink:
                        await telemetry_sink(s)

                async def _evt_sink(
                    e: ControlEvent,
                    buffer: list[ControlEvent] = event_buffer,
                ) -> None:
                    buffer.append(e)
                    if event_sink:
                        await event_sink(e)

                # Build grid and disturbance
                grid = GridModel(seeded_scenario.grid_params, mode=seeded_scenario.area_mode)
                disturbance = make_disturbance(seeded_scenario.disturbance, seed=seed)

                # Reset policy state for each run (create fresh instance of same type)
                fresh_policy = _clone_policy(policy, run_id, seeded_scenario)

                # Restoration policy is created by the policy object itself when the
                # simulation evaluates recovery conditions; we do not need a standalone
                # instance for the experiment loop.

                clock = SimulationClock(
                    scenario=seeded_scenario,
                    run_id=run_id,
                    grid=grid,
                    disturbance=disturbance,
                    buildings=buildings,
                    policy=fresh_policy,
                    telemetry_sink=_tel_sink,
                    event_sink=_evt_sink,
                )

                sim_result = await clock.run()

                # Compute metrics
                metrics = compute_all_metrics(sim_result, seeded_scenario, telemetry_buffer)
                sim_result.metrics = metrics

                policy_run_results.append(sim_result)
                all_metrics.append(metrics)

            result.policy_results[policy_name] = policy_run_results

            # Compute summary statistics
            nadir_vals = [m["frequency_nadir_hz"] for m in all_metrics]
            recovery_vals = [m["recovery_time_s"] for m in all_metrics if m["recovery_time_s"] >= 0]

            result.summary[policy_name] = PolicySummary(
                policy_name=policy_name,
                n_seeds=n_seeds,
                mean_nadir_hz=_mean(nadir_vals),
                mean_max_rocof_hz_per_s=_mean(
                    [m["max_rocof_hz_per_s"] for m in all_metrics]
                ),
                std_nadir_hz=_std(nadir_vals),
                ci95_nadir=_ci95(nadir_vals),
                mean_recovery_time_s=_mean(recovery_vals) if recovery_vals else None,
                mean_critical_ens_kwh=_mean([m["critical_ens_kwh"] for m in all_metrics]),
                mean_medical_load_interruption_s=_mean(
                    [m["medical_load_interruption_s"] for m in all_metrics]
                ),
                mean_feeder_trips=_mean([m["feeder_trips_count"] for m in all_metrics]),
                mean_rebound_peak_pu=_mean([m["rebound_peak_pu"] for m in all_metrics]),
                mean_jains_index=_mean([m["jains_fairness_index"] for m in all_metrics]),
                raw_metrics=all_metrics,
            )

        return result

    def to_json(self, result: ExperimentResult) -> str:
        """Serialise an ExperimentResult to JSON for export."""
        data = {
            "experiment_id": str(result.experiment_id),
            "scenario_name": result.scenario_name,
            "created_at": result.created_at.isoformat(),
            "schema_version": result.schema_version,
            "runs": {
                policy: [
                    {
                        "run_id": str(run.run_id),
                        "scenario_id": str(run.scenario_id),
                        "policy": run.policy,
                        "seed": run.seed,
                        "metrics": run.metrics,
                        "telemetry": [sample.model_dump(mode="json") for sample in run.telemetry],
                        "events": [event.model_dump(mode="json") for event in run.events],
                    }
                    for run in runs
                ]
                for policy, runs in result.policy_results.items()
            },
            "summary": {
                policy: {
                    "policy_name": s.policy_name,
                    "n_seeds": s.n_seeds,
                    "mean_nadir_hz": s.mean_nadir_hz,
                    "mean_max_rocof_hz_per_s": s.mean_max_rocof_hz_per_s,
                    "std_nadir_hz": s.std_nadir_hz,
                    "ci95_nadir": list(s.ci95_nadir),
                    "mean_recovery_time_s": s.mean_recovery_time_s,
                    "mean_critical_ens_kwh": s.mean_critical_ens_kwh,
                    "mean_medical_load_interruption_s": s.mean_medical_load_interruption_s,
                    "mean_feeder_trips": s.mean_feeder_trips,
                    "mean_rebound_peak_pu": s.mean_rebound_peak_pu,
                    "mean_jains_index": s.mean_jains_index,
                    "raw_metrics": s.raw_metrics,
                }
                for policy, s in result.summary.items()
            },
        }
        return json.dumps(data, indent=2)


def _clone_policy(
    policy: BasePolicy,
    run_id: uuid.UUID,
    scenario: ScenarioConfig,
) -> BasePolicy:
    """
    Create a fresh policy instance of the same type with a new run_id.
    This resets all per-run state (stage timers, trip sets, etc.).
    """
    from app.control.shedding_policy import ADMSFeederPolicy, PriorityEdgePolicy, UnmanagedPolicy

    if isinstance(policy, UnmanagedPolicy):
        return UnmanagedPolicy(run_id=run_id)
    if isinstance(policy, ADMSFeederPolicy):
        return ADMSFeederPolicy(
            feeder_groups=policy._feeder_groups,
            run_id=run_id,
            grid_params=scenario.grid_params,
            sample_interval_s=policy.sample_interval_s,
        )
    if isinstance(policy, PriorityEdgePolicy):
        restoration = policy.restoration_policy
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
            policy_name=policy.policy_name,
            enable_restoration=policy.restoration_enabled,
            restoration_policy=(
                StaggeredRestorationPolicy(
                    run_id=run_id,
                    t_stable_s=grid.t_stable_s,
                    f_recovery_hz=grid.f_recovery_hz,
                    f_freeze_hz=restoration.f_freeze_hz,
                    f_safe_hz=restoration.f_safe_hz,
                    H=restoration.H,
                    area_base_kw=area_base_kw,
                    up_reserve_pu=grid.up_reserve_pu,
                    base_delay_s=restoration.base_delay_s,
                    window_s=restoration.window_s,
                    stagger_enabled=restoration.stagger_enabled,
                    sample_interval_s=policy.sample_interval_s,
                )
                if restoration is not None
                else None
            ),
            grid_params=grid,
            sample_interval_s=policy.sample_interval_s,
        )
    # Fallback: return as-is (policy must be stateless)
    return policy
