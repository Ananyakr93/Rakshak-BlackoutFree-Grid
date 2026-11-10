"""Reproducible experiments for appliance lockout (E7) and restoration pickup (E8)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.control.restoration_policy import StaggeredRestorationPolicy
from app.control.shedding_policy import PriorityEdgePolicy
from app.evaluation.experiments import ExperimentRunner
from app.schemas.scenario import ScenarioConfig

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "backend" / "data" / "scenarios" / "default_scenario.yaml"
OUTPUT_DIR = Path(__file__).resolve().parent


def load_scenario() -> ScenarioConfig:
    with SCENARIO_PATH.open(encoding="utf-8") as file:
        return ScenarioConfig.model_validate(yaml.safe_load(file))


def compressor_scenario(lockout_s: float) -> ScenarioConfig:
    scenario = load_scenario()
    buildings = []
    for building in scenario.buildings:
        appliances = [
            item.model_copy(
                update={
                    "min_on_time_s": 0.0 if item.appliance_type.startswith("split_ac_") else item.min_on_time_s,
                    "min_off_time_s": 0.0 if item.appliance_type.startswith("split_ac_") else item.min_off_time_s,
                    "compressor_lockout_s": (
                        lockout_s if item.appliance_type.startswith("split_ac_") else item.compressor_lockout_s
                    ),
                }
            )
            for item in building.appliances
        ]
        buildings.append(building.model_copy(update={"appliances": appliances}))
    return scenario.model_copy(update={"buildings": buildings})


async def run_e7_e8() -> dict[str, object]:
    runner = ExperimentRunner()
    results: dict[str, object] = {}
    for label, lockout in (("without_lockout", 0.0), ("with_180s_lockout", 180.0)):
        result = await runner.run_experiment(
            compressor_scenario(lockout),
            [PriorityEdgePolicy(policy_name=label)],
            n_seeds=3,
        )
        results[label] = json.loads(runner.to_json(result))

    scenario = load_scenario()
    policies = [
        PriorityEdgePolicy(
            policy_name="synchronized_restore",
            restoration_policy=StaggeredRestorationPolicy(stagger_enabled=False),
        ),
        PriorityEdgePolicy(
            policy_name="staggered_restore",
            restoration_policy=StaggeredRestorationPolicy(stagger_enabled=True),
        ),
    ]
    results["restoration_comparison"] = json.loads(
        runner.to_json(
            await runner.run_experiment(scenario, policies, n_seeds=3)
        )
    )
    return {
        "experiment_ids": ["E7", "E8"],
        "assumption_note": (
            "Lockout, startup, and grid parameters are simulation assumptions, "
            "not measured Karnataka data."
        ),
        "results": results,
    }


if __name__ == "__main__":
    payload = asyncio.run(run_e7_e8())
    output = OUTPUT_DIR / "results_e7_e8.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"E7/E8 machine-readable results written to {output}")
