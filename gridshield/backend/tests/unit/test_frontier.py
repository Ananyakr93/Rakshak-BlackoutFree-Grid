"""Unit tests for participation-frontier analysis."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from app.control.shedding_policy import PriorityEdgePolicy, UnmanagedPolicy
from app.evaluation.experiments import ExperimentRunner
from app.evaluation.participation_frontier import compute_participation_frontier
from app.schemas.scenario import ScenarioConfig


def _default_scenario() -> ScenarioConfig:
    scenario_path = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "default_scenario.yaml"
    with scenario_path.open("r", encoding="utf-8") as handle:
        return ScenarioConfig(**yaml.safe_load(handle))


def test_participation_zero_matches_unmanaged() -> None:
    scenario = _default_scenario()
    frontier = compute_participation_frontier(
        scenario,
        participation_levels=[0.0],
        n_seeds=2,
        protection_criteria={"critical_ens_kwh": 0.0, "feeder_trips": 0},
    )

    runner = ExperimentRunner()
    result = asyncio.run(runner.run_experiment(scenario, [UnmanagedPolicy()], n_seeds=2))
    expected = result.summary["P0_unmanaged"]

    assert frontier.metrics_by_level[0.0].mean_nadir_hz == expected.mean_nadir_hz


def test_participation_full_matches_priority_edge() -> None:
    scenario = _default_scenario()
    frontier = compute_participation_frontier(
        scenario,
        participation_levels=[1.0],
        n_seeds=2,
        protection_criteria={"critical_ens_kwh": 0.0, "feeder_trips": 0},
    )

    runner = ExperimentRunner()
    result = asyncio.run(runner.run_experiment(scenario, [PriorityEdgePolicy()], n_seeds=2))
    expected = result.summary["P2_priority_edge"]

    assert frontier.metrics_by_level[1.0].mean_nadir_hz == expected.mean_nadir_hz


def test_p_star_is_in_range() -> None:
    scenario = _default_scenario()
    frontier = compute_participation_frontier(
        scenario,
        participation_levels=[0.0, 0.5, 1.0],
        n_seeds=2,
        protection_criteria={"critical_ens_kwh": 0.0, "feeder_trips": 0},
    )
    assert frontier.p_star is None or 0.0 <= frontier.p_star <= 1.0


def test_sensitivity_sweep_row_count() -> None:
    from experiments.sensitivity_analysis.run_e5 import run_sensitivity_sweeps

    rows = run_sensitivity_sweeps()
    expected_count = len([3.0, 4.0, 5.0, 6.0]) + len([1.0, 1.5, 2.0]) + len([0.05, 0.10, 0.15, 0.20, 0.25]) + len([0.03, 0.05, 0.07])
    assert len(rows) == expected_count
