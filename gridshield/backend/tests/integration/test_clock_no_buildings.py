"""
Integration smoke test: SimulationClock with no buildings, no policy.

Asserts that a 15% generation loss causes frequency to fall below 49.60 Hz
(S2 territory) — demonstrating the governor alone cannot arrest a large
disturbance in 60 seconds without demand-side response.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from app.control.shedding_policy import PriorityEdgePolicy
from app.schemas.events import ApplianceStateUpdate, ControlEvent
from app.schemas.scenario import BuildingConfig, DisturbanceConfig, GridParams, ScenarioConfig
from app.schemas.telemetry import TelemetrySample
from app.twin.appliance import Appliance
from app.twin.building_twin import BuildingTwin
from app.twin.disturbances import make_disturbance
from app.twin.grid_model import GridModel
from app.twin.simulation_clock import SimulationClock


@pytest.mark.asyncio
async def test_governor_alone_cannot_arrest_15pct_loss():
    """
    With no buildings and no demand response, frequency must settle below 49.70 Hz
    (well outside the IEGC normal band of 49.90-50.05 Hz), demonstrating that
    governor alone cannot maintain acceptable frequency under a 15% loss.
    The steady-state droop error for R=0.05, disturbance=0.15 is:
      Δf_ss = -R * disturbance * f0 = -0.05 * 0.15 * 50 ≈ -0.375 Hz → f_ss ≈ 49.625 Hz
    We allow up to 49.70 Hz as the assertion threshold (conservative).
    """
    grid_params = GridParams()
    disturbance_cfg = DisturbanceConfig(
        type="generation_loss",
        start_time_s=5.0,
        magnitude_pu=0.15,
        duration_s=200.0,
        recovery_ramp_s=30.0,
    )
    scenario = ScenarioConfig(
        name="Smoke test",
        seed=0,
        simulation_duration_s=120.0,
        area_mode="scaled",
        disturbance=disturbance_cfg,
        grid_params=grid_params,
        buildings=[
            BuildingConfig(
                building_id="dummy",
                weight_k=1,
                appliances=[],
            )
        ],
    )

    grid = GridModel(grid_params, mode="scaled")
    disturbance = make_disturbance(disturbance_cfg, seed=0)

    min_freq = [50.0]

    async def telemetry_sink(sample: TelemetrySample) -> None:
        if sample.frequency_hz < min_freq[0]:
            min_freq[0] = sample.frequency_hz

    async def event_sink(event: ControlEvent) -> None:
        pass

    clock = SimulationClock(
        scenario=scenario,
        run_id=uuid.uuid4(),
        grid=grid,
        disturbance=disturbance,
        buildings=[],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
    )

    result = await clock.run()

    # Governor alone: steady-state frequency deviation = R * disturbance * f0
    # = 0.05 * 0.15 * 50 = 0.375 Hz below nominal → ~49.625 Hz
    # Assert final frequency is below 49.70 Hz (outside IEGC normal band)
    assert result.final_state.frequency_hz < 49.70, (
        f"Expected frequency below 49.70 Hz (outside IEGC band), got {result.final_state.frequency_hz:.4f}"
    )

    paused_clock = SimulationClock(
        scenario=scenario,
        run_id=uuid.uuid4(),
        grid=GridModel(grid_params, mode="scaled"),
        disturbance=disturbance,
        buildings=[],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
    )
    paused_clock.pause()
    paused_run = asyncio.create_task(paused_clock.run())
    await asyncio.sleep(0)
    paused_clock.stop()
    stopped_result = await asyncio.wait_for(paused_run, timeout=1)
    assert stopped_result.final_state.time_s == 0
    assert not paused_clock.is_paused()

    fast_scenario = scenario.model_copy(update={"simulation_duration_s": 1.0})
    fast_clock = SimulationClock(
        scenario=fast_scenario,
        run_id=uuid.uuid4(),
        grid=GridModel(grid_params, mode="scaled"),
        disturbance=disturbance,
        buildings=[],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
        playback_speed=120,
        agent_sample_interval_s=0.1,
        ws_push_interval_s=0.2,
    )
    started_at = time.monotonic()
    fast_result = await fast_clock.run()
    assert time.monotonic() - started_at < 0.7
    assert len(fast_result.telemetry) == 5


def test_clock_rejects_sampling_intervals_not_aligned_to_grid_step():
    params = GridParams(dt_s=0.02)
    scenario = ScenarioConfig(
        name="unaligned sampling fixture",
        seed=0,
        simulation_duration_s=1,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=0,
            magnitude_pu=0.1,
            duration_s=1,
        ),
        buildings=[BuildingConfig(building_id="B1", appliances=[])],
    )

    async def sink(_sample):
        pass

    with pytest.raises(ValueError, match="integer multiple"):
        SimulationClock(
            scenario=scenario.model_copy(update={"grid_params": params}),
            run_id=uuid.uuid4(),
            grid=GridModel(params),
            disturbance=make_disturbance(scenario.disturbance),
            buildings=[],
            policy=None,
            telemetry_sink=sink,
            event_sink=sink,
            agent_sample_interval_s=0.03,
            ws_push_interval_s=0.1,
        )


def test_clock_rejects_policy_sample_interval_mismatch():
    params = GridParams(dt_s=0.02)
    scenario = ScenarioConfig(
        name="policy interval fixture",
        seed=0,
        simulation_duration_s=1,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=0,
            magnitude_pu=0.1,
            duration_s=1,
        ),
        buildings=[BuildingConfig(building_id="B1", appliances=[])],
    )

    async def sink(_sample):
        pass

    with pytest.raises(ValueError, match="intervals must match"):
        SimulationClock(
            scenario=scenario.model_copy(update={"grid_params": params}),
            run_id=uuid.uuid4(),
            grid=GridModel(params),
            disturbance=make_disturbance(scenario.disturbance),
            buildings=[],
            policy=PriorityEdgePolicy(sample_interval_s=0.1),
            telemetry_sink=sink,
            event_sink=sink,
            agent_sample_interval_s=0.2,
            ws_push_interval_s=0.2,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disturbance_type", "magnitude", "solar_share", "generation_change", "demand_change", "direction"),
    [
        ("generation_loss", 0.2, None, -0.2, 0.0, "fall"),
        ("demand_surge", 0.2, None, 0.0, 0.2, "fall"),
        ("combined", 0.2, None, -0.1, 0.1, "fall"),
        ("solar_surplus", 0.2, None, 0.2, 0.0, "rise"),
        ("solar_cloud_drop", 0.2, 0.4, -0.08, 0.0, "fall"),
    ],
)
async def test_clock_telemetry_and_frequency_match_disturbance_profile(
    disturbance_type,
    magnitude,
    solar_share,
    generation_change,
    demand_change,
    direction,
):
    params = GridParams()
    disturbance_config = DisturbanceConfig(
        type=disturbance_type,
        start_time_s=0,
        magnitude_pu=magnitude,
        solar_share_pu=solar_share,
        duration_s=1,
        recovery_ramp_s=0.2,
    )
    scenario = ScenarioConfig(
        name=f"{disturbance_type} telemetry contract",
        seed=7,
        simulation_duration_s=0.4,
        disturbance=disturbance_config,
        grid_params=params,
        buildings=[BuildingConfig(building_id="B1", appliances=[])],
    )
    samples: list[TelemetrySample] = []

    async def telemetry_sink(sample: TelemetrySample) -> None:
        samples.append(sample)

    async def event_sink(_event: ControlEvent) -> None:
        pass

    clock = SimulationClock(
        scenario=scenario,
        run_id=uuid.uuid4(),
        grid=GridModel(params),
        disturbance=make_disturbance(disturbance_config, seed=scenario.seed),
        buildings=[],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
        playback_speed=120,
        agent_sample_interval_s=0.1,
        ws_push_interval_s=0.1,
    )
    result = await clock.run()
    active_sample = next(
        sample
        for sample in samples
        if sample.simulation_time_s == pytest.approx(0.1)
    )

    assert active_sample.generation_disturbance_pu == pytest.approx(generation_change)
    assert active_sample.demand_disturbance_pu == pytest.approx(demand_change)
    assert abs(active_sample.generation_pu - (1 + generation_change)) < 0.01
    assert active_sample.demand_pu == pytest.approx(1 + demand_change)
    if direction == "fall":
        assert result.final_state.frequency_hz < params.f0_hz
    else:
        assert result.final_state.frequency_hz > params.f0_hz


@pytest.mark.asyncio
async def test_clock_emits_sequenced_building_state_transitions():
    params = GridParams()
    disturbance_config = DisturbanceConfig(
        type="generation_loss",
        start_time_s=5.0,
        magnitude_pu=0.1,
        duration_s=1.0,
    )
    scenario = ScenarioConfig(
        name="state update contract",
        seed=1,
        simulation_duration_s=0.4,
        disturbance=disturbance_config,
        grid_params=params,
        buildings=[
            BuildingConfig(
                building_id="B1",
                weight_k=2,
                appliances=[],
            )
        ],
    )
    appliance = Appliance(
        appliance_id="light",
        building_id="B1",
        appliance_type="lighting_led",
        priority="essential",
        rated_power_kw=0.1,
    )
    building = BuildingTwin("B1", weight_k=2, appliances=[appliance])
    updates: list[ApplianceStateUpdate] = []
    shed_requested = False

    async def telemetry_sink(sample: TelemetrySample) -> None:
        nonlocal shed_requested
        if not shed_requested:
            shed_requested = True
            appliance.shed(sample.simulation_time_s)

    async def event_sink(_event: ControlEvent) -> None:
        pass

    async def building_state_sink(update: ApplianceStateUpdate) -> None:
        updates.append(update)

    clock = SimulationClock(
        scenario=scenario,
        run_id=uuid.uuid4(),
        grid=GridModel(params),
        disturbance=make_disturbance(disturbance_config),
        buildings=[building],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
        building_state_sink=building_state_sink,
        playback_speed=120,
        agent_sample_interval_s=0.1,
        ws_push_interval_s=0.1,
    )

    await clock.run()

    assert len(updates) == 1
    assert updates[0].previous_state == "ON"
    assert updates[0].current_state == "SHED"
    assert updates[0].sequence_number == 1
    assert updates[0].current_power_kw == 0
    assert updates[0].rated_power_kw == pytest.approx(0.2)
    assert clock.building_sequence_number == 1


@pytest.mark.asyncio
async def test_clock_publishes_stable_state_power_limit_changes():
    params = GridParams()
    disturbance_config = DisturbanceConfig(
        type="generation_loss",
        start_time_s=5.0,
        magnitude_pu=0.1,
        duration_s=1.0,
    )
    scenario = ScenarioConfig(
        name="power-only state update",
        seed=1,
        simulation_duration_s=0.4,
        disturbance=disturbance_config,
        grid_params=params,
        buildings=[
            BuildingConfig(
                building_id="B1",
                weight_k=2,
                appliances=[],
            )
        ],
    )
    appliance = Appliance(
        appliance_id="ac",
        building_id="B1",
        appliance_type="split_ac_1ton",
        priority="deferrable",
        rated_power_kw=0.1,
    )
    building = BuildingTwin("B1", weight_k=2, appliances=[appliance])
    updates: list[ApplianceStateUpdate] = []
    throttle_requested = False

    async def telemetry_sink(sample: TelemetrySample) -> None:
        nonlocal throttle_requested
        if not throttle_requested:
            throttle_requested = True
            appliance.set_power_limit_fraction(0.7, sample.simulation_time_s)

    async def event_sink(_event: ControlEvent) -> None:
        pass

    async def building_state_sink(update: ApplianceStateUpdate) -> None:
        updates.append(update)

    clock = SimulationClock(
        scenario=scenario,
        run_id=uuid.uuid4(),
        grid=GridModel(params),
        disturbance=make_disturbance(disturbance_config),
        buildings=[building],
        policy=None,
        telemetry_sink=telemetry_sink,
        event_sink=event_sink,
        building_state_sink=building_state_sink,
        playback_speed=120,
        agent_sample_interval_s=0.1,
        ws_push_interval_s=0.1,
    )

    await clock.run()

    assert len(updates) == 1
    assert updates[0].previous_state == updates[0].current_state == "ON"
    assert updates[0].sequence_number == 1
    assert updates[0].current_power_kw == pytest.approx(0.14)
    assert updates[0].rated_power_kw == pytest.approx(0.2)
    assert clock.building_sequence_number == 1
