"""Sensitivity sweep for E5: H, D, disturbance magnitude and droop."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.control.shedding_policy import PriorityEdgePolicy, UnmanagedPolicy
from app.evaluation.experiments import ExperimentRunner
from app.schemas.scenario import ScenarioConfig


BASE_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = (
    BASE_DIR / "backend" / "data" / "scenarios" / "default_scenario.yaml"
)
OUTPUT_DIR = Path(__file__).resolve().parent


def _scenario_hash(scenario: ScenarioConfig) -> str:
    as_json = json.dumps(scenario.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(as_json.encode("utf-8")).hexdigest()


def _load_default_scenario() -> ScenarioConfig:
    with SCENARIO_PATH.open("r", encoding="utf-8") as handle:
        return ScenarioConfig(**yaml.safe_load(handle))


def _update_scenario_value(scenario: ScenarioConfig, parameter: str, value: float) -> ScenarioConfig:
    scenario_copy = deepcopy(scenario)
    if parameter == "H":
        return scenario_copy.model_copy(
            update={"grid_params": scenario_copy.grid_params.model_copy(update={"H": value})}
        )
    if parameter == "D":
        return scenario_copy.model_copy(
            update={"grid_params": scenario_copy.grid_params.model_copy(update={"D": value})}
        )
    if parameter == "disturbance.magnitude_pu":
        return scenario_copy.model_copy(
            update={"disturbance": scenario_copy.disturbance.model_copy(update={"magnitude_pu": value})}
        )
    if parameter == "R":
        return scenario_copy.model_copy(
            update={"grid_params": scenario_copy.grid_params.model_copy(update={"R": value})}
        )
    raise ValueError(f"Unsupported parameter: {parameter}")


def run_sensitivity_sweeps() -> list[dict[str, object]]:
    """Run the E5 param sweeps and return rows suitable for a CSV export."""
    sweeps = {
        "H": [3.0, 4.0, 5.0, 6.0],
        "D": [1.0, 1.5, 2.0],
        "disturbance.magnitude_pu": [0.05, 0.10, 0.15, 0.20, 0.25],
        "R": [0.03, 0.05, 0.07],
    }

    rows: list[dict[str, object]] = []
    runner = ExperimentRunner()

    for sweep_name, values in sweeps.items():
        for value in values:
            scenario = _update_scenario_value(_load_default_scenario(), sweep_name, value)
            result = __import__("asyncio").run(
                runner.run_experiment(
                    scenario_config=scenario,
                    policies=[UnmanagedPolicy(), PriorityEdgePolicy()],
                    n_seeds=3,
                )
            )
            p0_summary = result.summary["P0_unmanaged"]
            p2_summary = result.summary["P2_priority_edge"]
            row = {
                "sweep_name": sweep_name,
                "parameter_name": sweep_name,
                "parameter_value": value,
                "mean_frequency_nadir_hz_p0": p0_summary.mean_nadir_hz,
                "mean_frequency_nadir_hz_p2": p2_summary.mean_nadir_hz,
                "mean_recovery_time_s_p0": p0_summary.mean_recovery_time_s,
                "mean_recovery_time_s_p2": p2_summary.mean_recovery_time_s,
                "scenario_config_hash": _scenario_hash(scenario),
            }
            rows.append(row)
    return rows


def _write_csvs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = run_sensitivity_sweeps()
    per_sweep: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        per_sweep.setdefault(str(row["sweep_name"]), []).append(row)

    for sweep_name, sweep_rows in per_sweep.items():
        path = OUTPUT_DIR / f"{sweep_name}_sweep.csv"
        fieldnames = [
            "sweep_name",
            "parameter_name",
            "parameter_value",
            "mean_frequency_nadir_hz_p0",
            "mean_frequency_nadir_hz_p2",
            "mean_recovery_time_s_p0",
            "mean_recovery_time_s_p2",
            "scenario_config_hash",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sweep_rows)


if __name__ == "__main__":
    _write_csvs()
    print("Sensitivity analysis exported to experiments/sensitivity_analysis/")
