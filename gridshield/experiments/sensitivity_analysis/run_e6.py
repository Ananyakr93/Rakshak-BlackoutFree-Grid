"""Scalability sweep for E6: building count vs runtime and memory."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.control.shedding_policy import PriorityEdgePolicy
from app.evaluation.experiments import ExperimentRunner
from app.schemas.scenario import ScenarioConfig
from app.twin.indian_load_profiles import generate_building_config

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_PATH = BASE_DIR / "experiments" / "sensitivity_analysis" / "scalability_building_count.csv"


def _scenario_hash(scenario: ScenarioConfig) -> str:
    payload = json.dumps(scenario.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_scenario(
    building_count: int,
    seed: int,
    participation_level: float = 1.0,
) -> ScenarioConfig:
    if not 0.0 <= participation_level <= 1.0:
        raise ValueError("participation level must be between zero and one")
    buildings = []
    participating_count = int(round(building_count * participation_level))
    for idx in range(building_count):
        building_id = f"B{idx + 1}"
        building = generate_building_config(building_id, weight_k=1, seed=seed + idx)
        participating = idx < participating_count
        buildings.append(
            building.model_copy(
                update={
                    "appliances": [
                        appliance.model_copy(update={"enrolled": participating})
                        for appliance in building.appliances
                    ]
                }
            )
        )

    return ScenarioConfig(
        scenario_id=f"00000000-0000-0000-0000-{building_count:012d}",
        name=f"Scalability sweep: {building_count} buildings",
        description="Building-count scalability test for P2 policy",
        seed=seed,
        simulation_duration_s=180.0,
        area_mode="scaled",
        disturbance={
            "type": "generation_loss",
            "start_time_s": 10.0,
            "magnitude_pu": 0.15,
            "duration_s": 120.0,
            "recovery_ramp_s": 30.0,
        },
        grid_params={
            "H": 4.0,
            "D": 1.5,
            "R": 0.05,
            "deadband_hz": 0.03,
            "Tg": 0.1,
            "Tt": 0.4,
            "up_reserve_pu": 0.20,
            "down_reserve_pu": 0.10,
            "dt_s": 0.02,
            "f_s0_hz": 49.90,
            "f_s1_hz": 49.85,
            "f_s2_hz": 49.60,
            "f_s3_hz": 49.40,
            "f_o1_hz": 50.05,
            "f_o2_hz": 50.20,
            "rocof_s2_threshold": -0.3,
            "f_recovery_hz": 49.95,
            "t_stable_s": 60.0,
            "t_s0_hold_s": 10.0,
            "t_s1_hold_s": 5.0,
            "t_o1_hold_s": 30.0,
        },
        buildings=buildings,
    )


def run_scalability_sweep() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    runner = ExperimentRunner()

    for building_count in [12, 100, 500, 1000]:
        for participation_level in [0.5, 0.8, 1.0]:
            for seed in [42, 43, 44]:
                tracemalloc.start()
                start_ts = time.perf_counter()
                scenario = _build_scenario(building_count, seed, participation_level)
                result = __import__("asyncio").run(
                    runner.run_experiment(
                        scenario_config=scenario,
                        policies=[PriorityEdgePolicy()],
                        n_seeds=1,
                    )
                )
                elapsed = time.perf_counter() - start_ts
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                summary = result.summary["P2_priority_edge"]
                rows.append(
                    {
                        "building_count": building_count,
                        "participation_level": participation_level,
                        "appliance_count": sum(
                            len(building.appliances) for building in scenario.buildings
                        ),
                        "seed": seed,
                        "frequency_nadir_hz": summary.mean_nadir_hz,
                        "critical_ens_kwh": summary.mean_critical_ens_kwh,
                        "feeder_trips": summary.mean_feeder_trips,
                        "rebound_peak_pu": summary.mean_rebound_peak_pu,
                        "jains_fairness_index": summary.mean_jains_index,
                        "wall_clock_time_s": elapsed,
                        "peak_memory_bytes": peak,
                        "scenario_config_hash": _scenario_hash(scenario),
                    }
                )
    return rows


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = run_scalability_sweep()
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "building_count",
                "participation_level",
                "appliance_count",
                "seed",
                "frequency_nadir_hz",
                "critical_ens_kwh",
                "feeder_trips",
                "rebound_peak_pu",
                "jains_fairness_index",
                "wall_clock_time_s",
                "peak_memory_bytes",
                "scenario_config_hash",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Scalability export written to {OUTPUT_PATH}")
