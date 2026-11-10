"""Participation-frontier analysis for GridShield."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

from app.control.shedding_policy import PriorityEdgePolicy
from app.evaluation.experiments import ExperimentRunner, PolicySummary
from app.schemas.scenario import BuildingConfig, ScenarioConfig


@dataclass
class ParticipationFrontierResult:
    """Outcome of a participation-level sweep under P2 priority-edge control."""

    participation_levels: list[float]
    metrics_by_level: dict[float, PolicySummary]
    p_star: float | None
    criteria: dict[str, float | int]


def apply_participation_level(
    base_scenario: ScenarioConfig,
    participation_level: float,
) -> ScenarioConfig:
    """Return a copy of the scenario with a deterministic subset of buildings enrolled."""
    if participation_level < 0.0 or participation_level > 1.0:
        raise ValueError("participation_level must be between 0.0 and 1.0")

    building_ids = sorted(building.building_id for building in base_scenario.buildings)
    target_count = max(0, math.ceil(participation_level * len(building_ids)))
    selected = set(building_ids[:target_count])

    buildings = []
    for building in base_scenario.buildings:
        updated_appliances = [
            appliance.model_copy(update={"enrolled": building.building_id in selected})
            for appliance in building.appliances
        ]
        buildings.append(
            BuildingConfig(
                building_id=building.building_id,
                weight_k=building.weight_k,
                appliances=updated_appliances,
            )
        )

    return base_scenario.model_copy(update={"buildings": buildings})


def _passes_criteria(seed_metrics: dict[str, float], criteria: dict[str, float | int]) -> bool:
    """Check whether all criteria are satisfied for one seed result."""
    for key, threshold in criteria.items():
        normalized = key
        if normalized == "feeder_trips":
            normalized = "feeder_trips_count"
        if normalized == "critical_ens":
            normalized = "critical_ens_kwh"
        value = float(seed_metrics.get(normalized, 0.0))
        if value > float(threshold):
            return False
    return True


def compute_participation_frontier(
    base_scenario: ScenarioConfig,
    participation_levels: list[float],
    n_seeds: int = 10,
    protection_criteria: dict[str, float | int] | None = None,
) -> ParticipationFrontierResult:
    """Run P2 at each participation fraction and identify the minimum p* meeting the policy criteria."""
    criteria = protection_criteria or {"critical_ens_kwh": 0.0, "feeder_trips": 0}
    levels = sorted({float(level) for level in participation_levels})
    metrics_by_level: dict[float, PolicySummary] = {}
    satisfaction: dict[float, float] = {}

    for level in levels:
        scenario = apply_participation_level(base_scenario, level)
        runner = ExperimentRunner()
        result = asyncio.run(
            runner.run_experiment(
                scenario_config=scenario,
                policies=[PriorityEdgePolicy()],
                n_seeds=n_seeds,
            )
        )
        summary = result.summary.get("P2_priority_edge")
        if summary is None:
            raise ValueError("P2 priority-edge experiment did not return a summary")
        metrics_by_level[level] = summary

        seed_metrics = [
            per_seed.metrics
            for per_seed in result.policy_results.get("P2_priority_edge", [])
        ]
        if seed_metrics:
            satisfied = sum(
                1 for metrics in seed_metrics if _passes_criteria(metrics, criteria)
            )
            satisfaction[level] = satisfied / len(seed_metrics)
        else:
            satisfaction[level] = 0.0

    p_star: float | None = None
    for level in levels:
        if satisfaction.get(level, 0.0) >= 0.90:
            p_star = level
            break

    return ParticipationFrontierResult(
        participation_levels=levels,
        metrics_by_level=metrics_by_level,
        p_star=p_star,
        criteria=criteria,
    )
