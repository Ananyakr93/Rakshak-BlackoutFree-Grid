"""
Experiment runner for E1–E4: baseline, ADMS feeder, priority-edge, staggered restore.

Usage:
  cd gridshield/backend
  python ../experiments/baseline/run_e1_e4.py

Outputs:
  experiments/baseline/results_e1_e4.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import yaml

# Ensure backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.control.shedding_policy import ADMSFeederPolicy, PriorityEdgePolicy, UnmanagedPolicy
from app.evaluation.experiments import ExperimentRunner
from app.schemas.scenario import ScenarioConfig


SCENARIO_YAML = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "backend",
    "data",
    "scenarios",
    "default_scenario.yaml",
)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "results_e1_e4.json")


async def main() -> None:
    # Load scenario
    with open(SCENARIO_YAML) as f:
        data = yaml.safe_load(f)
    scenario = ScenarioConfig(**data)

    # Build policies
    building_ids = [b.building_id for b in scenario.buildings]
    feeder_groups = scenario.emulated_feeder_stages or {"stage1": building_ids}

    policies = [
        UnmanagedPolicy(),
        ADMSFeederPolicy(feeder_groups=feeder_groups),
        PriorityEdgePolicy(),
    ]

    runner = ExperimentRunner()
    print(f"\nRunning E1-E4 experiments: {len(policies)} policies × 3 seeds")
    print(f"Scenario: {scenario.name}")
    print("-" * 60)

    result = await runner.run_experiment(
        scenario_config=scenario,
        policies=policies,
        n_seeds=3,
    )

    # Print comparison table
    metrics_to_show = [
        ("frequency_nadir_hz", "Freq Nadir (Hz)"),
        ("critical_ens_kwh", "Critical ENS (kWh)"),
        ("feeder_trips_count", "Feeder Trips"),
        ("rebound_peak_pu", "Rebound Peak (pu)"),
        ("jains_fairness_index", "Jain's Index"),
    ]

    header = f"{'Metric':<30}" + "".join(f"{s.policy_name:<22}" for s in result.summary.values())
    print(header)
    print("-" * (30 + 22 * len(policies)))

    for key, label in metrics_to_show:
        row = f"{label:<30}"
        for summary in result.summary.values():
            if summary.raw_metrics:
                vals = [m.get(key, 0.0) for m in summary.raw_metrics]
                mean_val = sum(vals) / len(vals)
                row += f"{mean_val:<22.4f}"
            else:
                row += f"{'N/A':<22}"
        print(row)

    print("\n" + "-" * 60)
    print(f"P2 nadir: {result.summary.get('P2_priority_edge', {}).mean_nadir_hz if hasattr(result.summary.get('P2_priority_edge', object()), 'mean_nadir_hz') else 'N/A':.4f} Hz")

    # Export JSON
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(runner.to_json(result))
    print(f"\nResults exported to: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
