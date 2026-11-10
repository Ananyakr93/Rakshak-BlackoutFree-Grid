"""Compare centralized dispatch and distributed edge decisions under packet loss."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.control.shedding_policy import PriorityEdgePolicy
from app.evaluation.experiments import ExperimentRunner
from app.schemas.scenario import ScenarioConfig

ROOT = Path(__file__).resolve().parents[2]


async def run_e10() -> dict[str, object]:
    path = ROOT / "backend" / "data" / "scenarios" / "communication_fault_scenario.yaml"
    with path.open(encoding="utf-8") as file:
        base = ScenarioConfig.model_validate(yaml.safe_load(file))
    runner = ExperimentRunner()
    outcomes = {}
    for mode in ("CENTRALIZED", "DISTRIBUTED"):
        scenario = base.model_copy(update={"edge_mode": mode})
        policy = PriorityEdgePolicy(policy_name=mode.lower())
        result = await runner.run_experiment(scenario, [policy], n_seeds=3)
        outcomes[mode] = json.loads(runner.to_json(result))
    return {
        "experiment": "E10",
        "hypothesis": "Distributed edge decisions preserve local response during packet loss.",
        "controlled_variables": [
            "same communication-fault scenario",
            "same deterministic seeds",
            "same GridShield P2 thresholds",
        ],
        "results": outcomes,
        "assumption_note": "Communication loss is a seeded software simulation.",
    }


if __name__ == "__main__":
    payload = asyncio.run(run_e10())
    output = Path(__file__).with_name("results_e10.json")
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"E10 results written to {output}")
