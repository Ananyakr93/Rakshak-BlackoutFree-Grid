"""Contract tests for the dashboard's scenario, building, and results APIs."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.api.metrics import router as metrics_router
from app.api.runs import StartRunRequest, _make_policy, get_run, start_run
from app.api.runs import router as runs_router
from app.api.scenarios import router as scenarios_router
from app.api.websocket import router as websocket_router
from app.core.run_manager import RunEntry, run_manager
from app.schemas.events import ApplianceStateUpdate
from app.schemas.scenario import (
    ApplianceConfig as ScenarioApplianceConfig,
)
from app.schemas.scenario import (
    BuildingConfig as ScenarioBuildingConfig,
)
from app.schemas.scenario import (
    DisturbanceConfig,
    GridParams,
    ScenarioConfig,
)
from app.schemas.telemetry import TelemetrySample
from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(scenarios_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(metrics_router, prefix="/api/v1")
    app.include_router(websocket_router, prefix="/api/v1")
    return TestClient(app)


def _snapshot_clock(run_id: uuid.UUID, building: BuildingTwin) -> SimpleNamespace:
    def building_snapshots() -> list[dict]:
        return [
            {
                "run_id": run_id,
                "building_id": building.building_id,
                "weight_k": building.weight_k,
                "demand_kw": sum(
                    appliance.current_power_kw * building.weight_k
                    for appliance in building.appliances
                ),
                "simulation_time_s": 0.0,
                "sequence_number": 0,
                "updated_at": None,
                "appliances": [
                    {
                        "appliance_id": appliance.appliance_id,
                        "appliance_type": appliance.appliance_type,
                        "priority": appliance.priority,
                        "state": appliance.state.value,
                        "rated_power_kw": appliance.rated_power_kw * building.weight_k,
                        "current_power_kw": appliance.current_power_kw * building.weight_k,
                        "enrolled": appliance.enrolled,
                        "compressor_lockout_s": appliance.compressor_lockout_s,
                        "lockout_remaining_s": 0.0,
                        "inrush_multiplier": appliance.inrush_multiplier,
                        "inrush_duration_s": appliance.inrush_duration_s,
                    }
                    for appliance in building.appliances
                ],
            }
        ]

    return SimpleNamespace(building_snapshots=building_snapshots)


def test_scenario_templates_are_validated_and_include_building_data() -> None:
    response = _client().get("/api/v1/scenarios/templates")

    assert response.status_code == 200
    templates = response.json()
    assert {template["name"] for template in templates} == {
        "Communication Fault Test",
        "Default Generation Loss",
        "Severe Generation Loss Stress Test",
        "Solar Surplus Over-Frequency",
    }
    default = next(
        template for template in templates if template["template_id"] == "default_scenario"
    )
    assert len(default["config"]["buildings"]) == 12
    assert default["config"]["buildings"][0]["building_id"] == "B01"
    assert default["config"]["buildings"][0]["appliances"][0]["priority"] == "critical"
    for template in templates:
        config = template["config"]
        assert {
            "scenario_id",
            "name",
            "description",
            "seed",
            "simulation_duration_s",
            "area_mode",
            "edge_mode",
            "emulated_feeder_stages",
            "disturbance",
            "grid_params",
            "buildings",
            "fault_config",
        } == set(config)
        assert {
            "f0_hz",
            "H",
            "D",
            "R",
            "deadband_hz",
            "Tg",
            "Tt",
            "up_reserve_pu",
            "down_reserve_pu",
            "dt_s",
            "f_s0_hz",
            "f_s1_hz",
            "f_s2_hz",
            "f_s3_hz",
            "f_o1_hz",
            "f_o2_hz",
            "rocof_s2_threshold",
            "f_recovery_hz",
            "t_stable_s",
            "t_s0_hold_s",
            "t_s1_hold_s",
            "t_s2_hold_s",
            "t_s3_hold_s",
            "t_p1_recovery_s",
            "t_o1_hold_s",
        } == set(config["grid_params"])
        assert {
            "type",
            "start_time_s",
            "magnitude_pu",
            "duration_s",
            "recovery_ramp_s",
            "solar_share_pu",
        } == set(config["disturbance"])
        assert {
            "delay_range_s",
            "loss_probability",
            "duplicate_probability",
            "out_of_order",
            "shuffle_window_size",
        } == set(config["fault_config"])
        buildings = config["buildings"]
        assert len(buildings) >= 12
        assert len({building["building_id"] for building in buildings}) == len(buildings)
        assert all(
            len({item["appliance_id"] for item in building["appliances"]})
            == len(building["appliances"])
            for building in buildings
        )
        residential_ids = {"B02", "B03", "B05", "B06", "B07", "B11"}
        assert sum(
            building["weight_k"]
            for building in buildings
            if building["building_id"] in residential_ids
        ) == 500
        clinic = next(building for building in buildings if building["building_id"] == "B12")
        assert any(
            item["priority"] == "critical" and item["appliance_type"] == "medical_device"
            for item in clinic["appliances"]
        )
        assert all(
            set(item)
            == {
                "appliance_id",
                "appliance_type",
                "priority",
                "rated_power_kw",
                "min_on_time_s",
                "min_off_time_s",
                "max_shed_minutes",
                "enrolled",
                "initial_state",
                "compressor_lockout_s",
                "inrush_multiplier",
                "inrush_duration_s",
                "startup_recovery_profile",
            }
            for building in buildings
            for item in building["appliances"]
        )
        assert all(
            item["startup_recovery_profile"] in {"linear", "exponential"}
            for building in buildings
            for item in building["appliances"]
        )


def test_building_snapshot_uses_current_appliance_state(monkeypatch) -> None:
    run_id = uuid.uuid4()
    appliance = Appliance(
        appliance_id="B1_ev",
        building_id="B1",
        appliance_type="ev_charger",
        priority="deferrable",
        rated_power_kw=3.3,
        initial_state=ApplianceState.SHED,
    )
    building = BuildingTwin("B1", weight_k=2, appliances=[appliance])
    entry = SimpleNamespace(clock=_snapshot_clock(run_id, building))
    monkeypatch.setattr(
        run_manager, "get", lambda requested_id: entry if requested_id == run_id else None
    )

    response = _client().get(f"/api/v1/runs/{run_id}/buildings")

    assert response.status_code == 200
    snapshot = response.json()[0]
    assert snapshot["building_id"] == "B1"
    assert snapshot["weight_k"] == 2
    assert snapshot["demand_kw"] == 0
    assert snapshot["appliances"][0]["state"] == "SHED"
    assert snapshot["appliances"][0]["current_power_kw"] == 0
    assert snapshot["appliances"][0]["lockout_remaining_s"] == 0
    assert snapshot["run_id"] == str(run_id)
    assert snapshot["sequence_number"] == 0
    assert snapshot["updated_at"] is None


def test_building_snapshot_scales_power_for_represented_homes(monkeypatch) -> None:
    run_id = uuid.uuid4()
    appliance = Appliance(
        appliance_id="B1_load",
        building_id="B1",
        appliance_type="lighting_led",
        priority="essential",
        rated_power_kw=0.1,
    )
    building = BuildingTwin("B1", weight_k=12, appliances=[appliance])
    entry = SimpleNamespace(clock=_snapshot_clock(run_id, building))
    monkeypatch.setattr(
        run_manager, "get", lambda requested_id: entry if requested_id == run_id else None
    )

    response = _client().get(f"/api/v1/runs/{run_id}/buildings")

    assert response.status_code == 200
    snapshot = response.json()[0]
    assert snapshot["demand_kw"] == pytest.approx(1.2)
    assert snapshot["appliances"][0]["rated_power_kw"] == pytest.approx(1.2)
    assert snapshot["appliances"][0]["current_power_kw"] == pytest.approx(1.2)


def test_websocket_sends_initial_snapshot_and_replayed_state_updates(monkeypatch) -> None:
    run_id = uuid.uuid4()
    update = ApplianceStateUpdate(
        run_id=run_id,
        building_id="B1",
        appliance_id="light",
        appliance_type="lighting_led",
        priority="essential",
        previous_state="ON",
        current_state="SHED",
        current_power_kw=0,
        rated_power_kw=0.1,
        simulation_time_s=0.1,
        sequence_number=1,
    )
    snapshots = [
        {
            "run_id": run_id,
            "building_id": "B1",
            "weight_k": 1,
            "demand_kw": 0.1,
            "simulation_time_s": 0.0,
            "sequence_number": 0,
            "updated_at": None,
            "appliances": [],
        }
    ]
    clock = SimpleNamespace(
        building_sequence_number=1,
        building_snapshots=lambda initial=False: snapshots,
        current_state=lambda: SimpleNamespace(time_s=0.1),
    )
    entry = SimpleNamespace(clock=clock, status="running")
    queue = asyncio.Queue()
    monkeypatch.setattr(
        run_manager, "get", lambda requested_id: entry if requested_id == run_id else None
    )
    monkeypatch.setattr(
        run_manager, "subscribe_ws", lambda requested_id: queue if requested_id == run_id else None
    )
    monkeypatch.setattr(run_manager, "unsubscribe_ws", lambda *_args: None)
    monkeypatch.setattr(
        run_manager,
        "building_updates_after",
        lambda requested_id, _sequence: (1, [update]) if requested_id == run_id else (None, []),
    )

    with _client().websocket_connect(
        f"/api/v1/runs/{run_id}/stream?after_sequence=0"
    ) as websocket:
        initial = websocket.receive_json()
        replayed = websocket.receive_json()

    assert initial["type"] == "building_snapshot"
    assert initial["sequence_number"] == 0
    assert initial["buildings"][0]["run_id"] == str(run_id)
    assert replayed["type"] == "building_state_update"
    assert replayed["sequence_number"] == 1
    assert replayed["current_state"] == "SHED"


def test_saved_experiment_results_are_labeled_by_actual_policy() -> None:
    response = _client().get("/api/v1/experiments/baseline")

    assert response.status_code == 200
    assert set(response.json()["summary"]) == {
        "P0_unmanaged",
        "P1_adms_feeder",
        "P2_priority_edge",
    }


def test_playback_controls_pause_resume_and_update_speed(monkeypatch) -> None:
    run_id = uuid.uuid4()

    class FakeClock:
        paused = False
        speed = 30.0

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def set_playback_speed(self, speed):
            self.speed = speed

        def is_paused(self):
            return self.paused

    entry = SimpleNamespace(status="running", clock=FakeClock(), playback_speed=30.0)
    monkeypatch.setattr(run_manager, "get", lambda requested_id: entry if requested_id == run_id else None)
    persisted_statuses = []

    async def update_run_status(_session, _run_id, status):
        persisted_statuses.append(status)

    monkeypatch.setattr("app.api.runs.repository.update_run_status", update_run_status)
    client = _client()

    paused = client.post(f"/api/v1/runs/{run_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    changed = client.post(
        f"/api/v1/runs/{run_id}/speed",
        json={"playback_speed": 5},
    )
    assert changed.status_code == 200
    assert changed.json()["playback_speed"] == 5

    resumed = client.post(f"/api/v1/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"
    assert entry.clock.paused is False
    assert entry.clock.speed == 5
    assert persisted_statuses == ["paused", "running"]


@pytest.mark.asyncio
async def test_run_seed_override_is_saved_and_passed_to_simulation(monkeypatch) -> None:
    scenario = ScenarioConfig(
        name="seed override",
        seed=17,
        simulation_duration_s=10,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=1,
            magnitude_pu=0.1,
            duration_s=5,
        ),
        buildings=[ScenarioBuildingConfig(building_id="B1", appliances=[])],
    )
    scenario_id = scenario.scenario_id
    persisted: dict[str, object] = {}

    async def get_scenario(_session, _scenario_id):
        return SimpleNamespace(config_json=scenario.model_dump_json())

    async def create_run(_session, requested_id, policy, seed, config_snapshot):
        persisted["scenario_id"] = requested_id
        persisted["policy"] = policy
        persisted["seed"] = seed
        persisted["snapshot_seed"] = config_snapshot.seed
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr("app.api.runs.repository.get_scenario", get_scenario)
    monkeypatch.setattr("app.api.runs.repository.create_run", create_run)
    monkeypatch.setattr(
        run_manager,
        "register",
        lambda *_args: SimpleNamespace(playback_speed=None, hil_building_id=None),
    )
    background_tasks = BackgroundTasks()

    response = await start_run(
        StartRunRequest(
            scenario_id=scenario_id,
            policy="P2_priority_edge",
            seed=902,
        ),
        background_tasks,
        session=object(),
    )

    assert response["status"] == "pending"
    assert persisted == {
        "scenario_id": scenario_id,
        "policy": "P2_priority_edge",
        "seed": 902,
        "snapshot_seed": 902,
    }
    assert background_tasks.tasks[0].args[1].seed == 902


def test_run_snapshot_returns_the_persisted_effective_scenario(monkeypatch) -> None:
    run_id = uuid.uuid4()
    scenario = ScenarioConfig(
        name="effective configuration",
        seed=17,
        simulation_duration_s=900,
        edge_mode="CENTRALIZED",
        emulated_feeder_stages={"stage2": ["B1"]},
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=10,
            magnitude_pu=0.2,
            duration_s=40,
        ),
        grid_params=GridParams(
            H=5.0,
            deadband_hz=0.04,
            up_reserve_pu=0.25,
            dt_s=0.01,
        ),
        buildings=[
            ScenarioBuildingConfig(
                building_id="B1",
                appliances=[
                    ScenarioApplianceConfig(
                        appliance_id="B1_AC",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                        startup_recovery_profile="exponential",
                    )
                ],
            )
        ],
    )
    record = SimpleNamespace(
        status="completed",
        scenario_id=scenario.scenario_id,
        config_snapshot_json=scenario.model_dump_json(),
        policy="P1_adms_feeder",
        seed=scenario.seed,
    )

    async def get_run_record(_session, requested_id):
        assert requested_id == run_id
        return record

    monkeypatch.setattr("app.api.runs.repository.get_run", get_run_record)
    monkeypatch.setattr(run_manager, "get_run_state", lambda _run_id: None)

    response = asyncio.run(get_run(run_id, session=object()))

    assert response["scenario"] == scenario.model_dump(mode="json")
    assert response["policy"] == "P1_adms_feeder"
    assert response["scenario"]["emulated_feeder_stages"] == {"stage2": ["B1"]}
    assert response["scenario"]["grid_params"]["up_reserve_pu"] == 0.25
    assert response["scenario"]["buildings"][0]["appliances"][0][
        "startup_recovery_profile"
    ] == "exponential"


def test_playback_speed_rejects_out_of_range_value(monkeypatch) -> None:
    run_id = uuid.uuid4()
    entry = SimpleNamespace(
        status="running",
        clock=SimpleNamespace(set_playback_speed=lambda _speed: None),
        playback_speed=30.0,
    )
    monkeypatch.setattr(run_manager, "get", lambda requested_id: entry if requested_id == run_id else None)

    response = _client().post(
        f"/api/v1/runs/{run_id}/speed",
        json={"playback_speed": 500},
    )

    assert response.status_code == 422


def test_integration_status_and_simulated_nilm_are_explicit(monkeypatch) -> None:
    run_id = uuid.uuid4()
    clock = SimpleNamespace(
        hil_adapter=None,
        nilm_events=lambda: [{
            "simulation_time_s": 1.0,
            "building_id": "B02",
            "delta_power_kw": -1.0,
            "event_type": "switch_off",
            "appliance_type": "split_ac_1ton",
            "confidence": 1.0,
            "classification": "classified",
            "source": "simulated_aggregate_load",
        }],
    )
    entry = SimpleNamespace(clock=clock, hil_building_id=None)
    monkeypatch.setattr(run_manager, "get", lambda requested_id: entry if requested_id == run_id else None)
    client = _client()

    integrations = client.get(f"/api/v1/runs/{run_id}/integrations")
    estimates = client.get(f"/api/v1/runs/{run_id}/nilm")

    assert integrations.status_code == 200
    assert integrations.json()["hil"]["status"] == "not_configured"
    assert integrations.json()["nilm"]["source"] == "simulated_aggregate_load"
    assert estimates.status_code == 200
    assert estimates.json()[0]["source"] == "simulated_aggregate_load"


def test_diagnostics_endpoints_report_simulated_subsystems(monkeypatch) -> None:
    run_id = uuid.uuid4()
    building = BuildingTwin(
        "B1",
        appliances=[Appliance("ac", "B1", "split_ac_1ton", "deferrable", 1.0)],
    )
    clock = SimpleNamespace(
        buildings=[building],
        agent_status=lambda: [{
            "building_id": "B1",
            "operating_mode": "DISTRIBUTED",
            "communication_available": True,
            "evaluations": 2,
            "last_decision": "monitor",
            "last_decision_reason": "No protection action was required.",
            "last_decision_time_s": 1.0,
            "autonomous": True,
        }],
        restoration_status=lambda: {
            "enabled": False,
            "frozen": False,
            "frequency_hz": 50.0,
            "frequency_gate_hz": 49.95,
            "freeze_below_hz": 49.85,
            "projection_floor_hz": 49.90,
            "stable_timer_s": 0.0,
            "required_stability_s": 60.0,
            "stagger_enabled": False,
            "queue": [],
        },
    )
    entry = SimpleNamespace(clock=clock)
    monkeypatch.setattr(run_manager, "get", lambda requested_id: entry if requested_id == run_id else None)
    client = _client()

    agents = client.get(f"/api/v1/runs/{run_id}/agents")
    restoration = client.get(f"/api/v1/runs/{run_id}/restoration")
    feeder = client.get(f"/api/v1/runs/{run_id}/feeder")

    assert agents.status_code == 200
    assert agents.json()[0]["last_decision"] == "monitor"
    assert restoration.status_code == 200
    assert restoration.json()["enabled"] is False
    assert feeder.status_code == 200
    assert feeder.json()["source"] == "simulated_load_estimate"
    assert feeder.json()["branches"][0]["estimated_current_a"] > 0


def test_live_comparison_runs_all_four_modes_over_paired_seeds() -> None:
    scenario = ScenarioConfig(
        name="four-mode contract",
        seed=4,
        simulation_duration_s=1.0,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=0.1,
            magnitude_pu=0.1,
            duration_s=0.5,
        ),
        buildings=[
            ScenarioBuildingConfig(
                building_id="B1",
                appliances=[
                    ScenarioApplianceConfig(
                        appliance_id="B1_AC",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                    )
                ],
            )
        ],
    )

    response = _client().post(
        "/api/v1/experiments/compare",
        json={"scenario": scenario.model_dump(mode="json"), "n_seeds": 2},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["seed_range"] == [4, 5]
    assert set(result["summary"]) == {
        "P0_unmanaged",
        "P1_adms_feeder",
        "P2_priority_edge",
        "P2_priority_edge_synchronized",
    }
    assert all(summary["n_seeds"] == 2 for summary in result["summary"].values())
    assert len(result["frequency_trajectories"]) == 4
    assert all(
        "mean_medical_load_interruption_s" in summary
        and "mean_max_rocof_hz_per_s" in summary
        for summary in result["summary"].values()
    )


def test_live_telemetry_exposes_disturbance_components(monkeypatch) -> None:
    run_id = uuid.uuid4()
    entry = RunEntry(run_id=run_id, policy="P0_unmanaged")
    entry.telemetry_buffer.append(
        TelemetrySample(
            run_id=run_id,
            simulation_time_s=1.0,
            frequency_hz=49.9,
            generation_pu=0.9,
            demand_pu=1.1,
            generation_disturbance_pu=-0.1,
            demand_disturbance_pu=0.1,
            frequency_stage="normal",
            rocof_hz_per_s=-0.1,
            sequence_number=1,
        )
    )
    monkeypatch.setattr(run_manager, "_runs", {run_id: entry})

    response = _client().get(f"/api/v1/runs/{run_id}/telemetry")

    assert response.status_code == 200
    assert response.json()[0]["generation_disturbance_pu"] == -0.1
    assert response.json()[0]["demand_disturbance_pu"] == 0.1


def test_policy_factory_passes_scenario_protection_and_recovery_settings() -> None:
    grid_params = GridParams(
        H=6.0,
        f_s1_hz=49.9,
        t_s1_hold_s=1.5,
        t_s2_hold_s=4.0,
        t_s3_hold_s=1.0,
        t_p1_recovery_s=90.0,
        t_stable_s=45.0,
    )
    scenario = ScenarioConfig(
        name="policy settings",
        seed=7,
        simulation_duration_s=120.0,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=1.0,
            magnitude_pu=0.1,
            duration_s=10.0,
        ),
        grid_params=grid_params,
        buildings=[
            ScenarioBuildingConfig(
                building_id="B1",
                appliances=[
                    ScenarioApplianceConfig(
                        appliance_id="B1_AC",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                    )
                ],
            )
        ],
    )

    p1 = _make_policy("P1_adms_feeder", uuid.uuid4(), ["B1"], scenario)
    p2 = _make_policy("P2_priority_edge", uuid.uuid4(), ["B1"], scenario)
    synchronized = _make_policy(
        "P2_priority_edge_synchronized", uuid.uuid4(), ["B1"], scenario
    )
    p3 = _make_policy(
        "P3_priority_edge_no_restoration", uuid.uuid4(), ["B1"], scenario
    )

    assert p1.grid_params == grid_params
    assert p2.grid_params == grid_params
    assert p2.restoration_policy.H == grid_params.H
    assert p2.restoration_policy.t_stable_s == grid_params.t_stable_s
    assert synchronized.restoration_enabled is True
    assert synchronized.restoration_policy.stagger_enabled is False
    assert p3.restoration_enabled is False
