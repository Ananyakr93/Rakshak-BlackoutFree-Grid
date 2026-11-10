"""
Unit tests for shedding and restoration policies (Prompt 6).

Tests:
  1. UnmanagedPolicy never sheds any appliance
  2. ADMSFeederPolicy trips entire feeder including Critical at S1
  3. PriorityEdgePolicy at S1 only sheds Deferrable
  4. PriorityEdgePolicy at S3 sheds Essential but never Critical
  5. StaggeredRestorationPolicy does not restore if f < 49.95 Hz
  6. StaggeredRestorationPolicy produces different delays for different building_ids
  7. Restoration is frozen when frequency relapses below 49.85 Hz
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest

from app.control.edge_agent import EdgeAgent, OperatingMode
from app.control.restoration_policy import StaggeredRestorationPolicy, _stagger_delay
from app.control.shedding_policy import (
    ADMSFeederPolicy,
    PriorityEdgePolicy,
    UnmanagedPolicy,
)
from app.schemas.scenario import GridParams, ScenarioConfig
from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin
from app.twin.grid_model import GridModel, GridState
from app.twin.simulation_clock import _restoration_incident_id


def _make_state(
    freq: float,
    rocof: float = 0.0,
    demand_pu: float = 1.0,
    generation_disturbance_pu: float = 0.0,
) -> GridState:
    return GridState(
        time_s=100.0,
        frequency_hz=freq,
        delta_omega=(freq - 50.0) / 50.0,
        delta_Pm=0.0,
        delta_Pg=0.0,
        demand_pu=demand_pu,
        generation_pu=1.0,
        disturbance_pu=0.0,
        rocof_hz_per_s=rocof,
        generation_disturbance_pu=generation_disturbance_pu,
    )


def _make_building(building_id: str = "B1") -> BuildingTwin:
    """Building with one appliance of each priority tier."""
    appl_crit = Appliance("crit", building_id, "medical", "critical", 0.5, enrolled=True)
    appl_ess = Appliance("ess", building_id, "fan", "essential", 0.2, enrolled=True)
    appl_def = Appliance("def", building_id, "ac", "deferrable", 1.0, enrolled=True)
    return BuildingTwin(building_id=building_id, appliances=[appl_crit, appl_ess, appl_def])


def test_restoration_incident_id_is_stable_across_run_scenario_ids():
    scenario = ScenarioConfig(
        name="repeatable",
        seed=17,
        simulation_duration_s=10,
        disturbance={
            "type": "generation_loss",
            "start_time_s": 1,
            "magnitude_pu": 0.1,
            "duration_s": 5,
        },
        buildings=[{"building_id": "B1", "appliances": []}],
    )
    replay = scenario.model_copy(update={"scenario_id": uuid.uuid4()})
    incident_id = _restoration_incident_id(scenario)
    replay_incident_id = _restoration_incident_id(replay)

    assert incident_id == replay_incident_id
    assert _stagger_delay("B1", incident_id, scenario.seed) == _stagger_delay(
        "B1", replay_incident_id, replay.seed
    )


# --------------------------------------------------------------------------
# Test 1: UnmanagedPolicy never sheds
# --------------------------------------------------------------------------
def test_unmanaged_policy_never_sheds():
    policy = UnmanagedPolicy()
    b = _make_building()
    # Even at very low frequency
    state = _make_state(49.0)
    delta, events = policy.evaluate(state, b, 100.0)
    assert delta == 0.0
    for a in b.appliances:
        assert a.state == ApplianceState.ON, f"{a.appliance_id} was shed by unmanaged policy"
    assert any(event.event_type == "no_op" for event in events)


def test_unmanaged_policy_does_not_repeat_low_frequency_no_ops():
    policy = UnmanagedPolicy()
    building = _make_building()
    state = _make_state(49.0)

    _, first_events = policy.evaluate(state, building, 100.0)
    _, second_events = policy.evaluate(state, building, 100.5)
    _, recovered_events = policy.evaluate(_make_state(50.0), building, 101.0)
    _, next_incident_events = policy.evaluate(state, building, 101.5)

    assert len(first_events) == 1
    assert second_events == []
    assert recovered_events == []
    assert len(next_incident_events) == 1


# --------------------------------------------------------------------------
# Test 2: ADMS trips entire feeder including Critical
# --------------------------------------------------------------------------
def test_adms_trips_critical_at_s1():
    policy = ADMSFeederPolicy(feeder_groups={"stage1": ["B1"]})
    b = _make_building("B1")
    state_low = _make_state(49.84)  # below 49.85

    # Simulate 6 ticks of 0.5s each (3s total) to accumulate hold time beyond 5s
    all_events = []
    for tick in range(12):  # 12 * 0.5s = 6s > 5s hold
        delta, events = policy.evaluate(state_low, b, 100.0 + tick * 0.5)
        all_events.extend(events)

    # Feeder should have tripped — Critical appliance must be SHED
    critical = next(a for a in b.appliances if a.priority == "critical")
    assert (
        critical.state == ApplianceState.SHED
    ), "P1 must shed Critical appliance (no priority awareness in feeder trip)"
    feeder_events = [event for event in all_events if event.event_type == "feeder_trip"]
    assert {event.appliance_id for event in feeder_events} == {
        appliance.appliance_id for appliance in b.appliances
    }
    critical_trip = next(event for event in feeder_events if event.priority == "critical")
    assert critical_trip.power_delta_kw == 0.5
    assert "P1 ADMS feeder trip stage1" in critical_trip.reason


@pytest.mark.parametrize("stage", ["stage1", "stage2", "stage3"])
def test_adms_zero_hold_does_not_trip_above_stage_threshold(stage):
    params = GridParams(
        t_s1_hold_s=0.0,
        t_s2_hold_s=0.0,
        t_s3_hold_s=0.0,
    )
    policy = ADMSFeederPolicy(
        feeder_groups={stage: ["B1"]},
        grid_params=params,
    )
    building = _make_building("B1")

    _, events = policy.evaluate(_make_state(50.0), building, 100.0)

    assert not any(event.event_type == "feeder_trip" for event in events)
    assert all(appliance.state == ApplianceState.ON for appliance in building.appliances)


@pytest.mark.parametrize(
    ("stage", "frequency"),
    [("stage1", 49.84), ("stage2", 49.59), ("stage3", 49.39)],
)
def test_adms_zero_hold_trips_when_stage_threshold_is_crossed(stage, frequency):
    params = GridParams(
        t_s1_hold_s=0.0,
        t_s2_hold_s=0.0,
        t_s3_hold_s=0.0,
    )
    policy = ADMSFeederPolicy(
        feeder_groups={stage: ["B1"]},
        grid_params=params,
    )
    building = _make_building("B1")

    _, events = policy.evaluate(_make_state(frequency), building, 100.0)

    assert {event.event_type for event in events} == {"feeder_trip"}
    assert all(appliance.state == ApplianceState.SHED for appliance in building.appliances)


# --------------------------------------------------------------------------
# Test 3: P2 at S1 only sheds Deferrable
# --------------------------------------------------------------------------
def test_p2_s1_only_sheds_deferrable():
    policy = PriorityEdgePolicy()
    b = _make_building()
    state = _make_state(49.84)  # below 49.85

    # Need to accumulate 5s hold time → 10 ticks of 0.5s
    for i in range(12):
        delta, events = policy.evaluate(state, b, float(i))

    deferrable = next(a for a in b.appliances if a.priority == "deferrable")
    essential = next(a for a in b.appliances if a.priority == "essential")
    critical = next(a for a in b.appliances if a.priority == "critical")

    assert deferrable.state == ApplianceState.SHED, "Deferrable should be shed at S1"
    assert essential.state == ApplianceState.ON, "Essential must NOT be shed at S1"
    assert critical.state == ApplianceState.ON, "Critical must NEVER be shed"


def test_priority_edge_uses_scenario_protection_thresholds():
    policy = PriorityEdgePolicy(
        grid_params=GridParams(f_s1_hz=49.90, t_s1_hold_s=0.0)
    )
    building = _make_building()

    _, events = policy.evaluate(_make_state(49.89), building, 100.0)

    deferrable = next(
        item for item in building.appliances if item.priority == "deferrable"
    )
    assert deferrable.state == ApplianceState.SHED
    assert any("49.90" in event.reason for event in events)


def test_p2_s0_throttle_persists_until_frequency_recovers():
    params = GridParams(t_s0_hold_s=0.0)
    policy = PriorityEdgePolicy(grid_params=params)
    building = _make_building()
    deferrable = next(
        appliance for appliance in building.appliances
        if appliance.priority == "deferrable"
    )

    demand_delta, events = policy.evaluate(_make_state(49.89), building, 100.0)

    assert deferrable.current_power_kw == 0.7
    assert demand_delta == pytest.approx(-0.3)
    throttle_event = next(
        event for event in events if event.event_type == "throttle_deferrable"
    )
    assert throttle_event.power_delta_kw == pytest.approx(0.3)
    deferrable.tick(100.5, 0.5)
    assert deferrable.current_power_kw == 0.7

    restored_delta, _ = policy.evaluate(_make_state(49.95), building, 101.0)

    assert deferrable.current_power_kw == 1.0
    assert restored_delta == pytest.approx(0.3)


def test_p2_o1_absorbs_an_enrolled_off_deferrable_load():
    policy = PriorityEdgePolicy(
        grid_params=GridParams(f_o1_hz=50.05, t_o1_hold_s=0.0),
    )
    building = BuildingTwin(
        building_id="B1",
        appliances=[
            Appliance(
                "off-ac",
                "B1",
                "split_ac_1ton",
                "deferrable",
                1.0,
                enrolled=True,
                initial_state=ApplianceState.OFF,
            ),
        ],
    )

    demand_delta, events = policy.evaluate(_make_state(50.10), building, 100.0)

    appliance = building.appliances[0]
    assert appliance.state in {ApplianceState.RUNNING, ApplianceState.ON}
    assert demand_delta > 0
    assert any(event.event_type == "absorb_deferrable" for event in events)


def test_adms_hold_timer_advances_once_per_sample_across_buildings():
    building_ids = [f"B{index:02}" for index in range(12)]
    buildings = [_make_building(building_id) for building_id in building_ids]
    policy = ADMSFeederPolicy(feeder_groups={"stage1": building_ids})
    low_frequency = _make_state(49.84)

    for tick in range(1, 10):
        for building in buildings:
            policy.evaluate(low_frequency, building, tick * 0.5)

    assert all(
        appliance.state in {ApplianceState.ON, ApplianceState.RUNNING}
        for building in buildings
        for appliance in building.appliances
    )

    for building in buildings:
        policy.evaluate(low_frequency, building, 5.0)

    assert all(
        appliance.state == ApplianceState.SHED
        for building in buildings
        for appliance in building.appliances
    )


# --------------------------------------------------------------------------
# Test 4: P2 at S3 sheds Essential but never Critical
# --------------------------------------------------------------------------
def test_p2_s3_sheds_essential_not_critical():
    policy = PriorityEdgePolicy()
    b = _make_building()
    state = _make_state(49.39)  # below 49.40 (S3)

    delta, events = policy.evaluate(state, b, 100.0)

    critical = next(a for a in b.appliances if a.priority == "critical")
    essential = next(a for a in b.appliances if a.priority == "essential")

    assert critical.state == ApplianceState.ON, "Critical must NEVER be shed at S3"
    assert essential.state == ApplianceState.SHED, "Essential should be shed at S3"


def test_priority_edge_can_disable_restoration_without_disabling_shedding():
    policy = PriorityEdgePolicy(enable_restoration=False)

    assert policy.restoration_policy is None
    assert policy.restoration_enabled is False


# --------------------------------------------------------------------------
# Test 5: StaggeredRestorationPolicy does NOT restore if f < 49.95 Hz
# --------------------------------------------------------------------------
def test_staggered_restore_blocked_below_recovery_band():
    policy = StaggeredRestorationPolicy(t_stable_s=0.0, f_recovery_hz=49.95)
    b = _make_building()
    # Put deferrable in WAITING_RESTORATION
    deferred = next(a for a in b.appliances if a.priority == "deferrable")
    deferred.shed(sim_time_s=0.0)
    deferred.mark_waiting_restoration(sim_time_s=0.0)

    state = _make_state(49.90)  # below 49.95 → no restore
    events = policy.tick(state, [b], "incident1", 42, sim_time_s=100.0)
    assert deferred.state == ApplianceState.WAITING_RESTORATION
    restore_events = [e for e in events if e.event_type == "restore"]
    assert len(restore_events) == 0


def test_restoration_snapshot_exposes_waiting_queue_and_gate_values():
    policy = StaggeredRestorationPolicy(
        t_stable_s=2.0,
        f_recovery_hz=49.95,
        base_delay_s=5.0,
        window_s=1,
    )
    building = _make_building("B1")
    appliance = next(item for item in building.appliances if item.priority == "deferrable")
    appliance.shed(0.0)
    appliance.mark_waiting_restoration(0.0)
    policy.tick(_make_state(49.96), [building], "incident", 42, 10.0)

    snapshot = policy.snapshot(_make_state(49.96), [building], "incident", 42)

    assert snapshot["enabled"] is True
    assert snapshot["stable_timer_s"] == 0.5
    queue = snapshot["queue"]
    assert len(queue) == 1
    assert queue[0]["building_id"] == "B1"
    assert queue[0]["stagger_delay_s"] == 5.0
    assert queue[0]["ready"] is False


# --------------------------------------------------------------------------
# Test 6: Different building_ids produce different stagger delays
# --------------------------------------------------------------------------
def test_stagger_delay_differs_by_building_id():
    delay1 = _stagger_delay("B1", "incident1", 42)
    delay2 = _stagger_delay("B2", "incident1", 42)
    delay3 = _stagger_delay("B3", "incident1", 42)
    delays = {delay1, delay2, delay3}
    # At least 2 of 3 should be distinct
    assert len(delays) >= 2, f"Expected different delays, got {delays}"


def test_stagger_delay_is_appliance_specific_within_building():
    delay1 = _stagger_delay(
        "B1", "incident1", 42, window_s=1000, appliance_id="load-1"
    )
    delay2 = _stagger_delay(
        "B1", "incident1", 42, window_s=1000, appliance_id="load-2"
    )

    assert delay1 != delay2


def test_synchronized_restoration_splits_unsafe_combined_pickup():
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.95,
        f_safe_hz=49.95,
        H=4.0,
        area_base_kw=2.0,
        base_delay_s=0.0,
        stagger_enabled=False,
    )
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance("load-1", "B1", "fan", "deferrable", 0.5),
            Appliance("load-2", "B1", "heater", "deferrable", 0.5),
        ],
    )
    for appliance in building.appliances:
        appliance.shed(0.0)
        appliance.mark_waiting_restoration(0.0)

    events = policy.tick(
        _make_state(49.99, demand_pu=0.7), [building], "incident", 1, 10.0
    )

    assert [event.event_type for event in events] == ["restore"]
    assert sum(
        appliance.state == ApplianceState.ON for appliance in building.appliances
    ) == 1


# --------------------------------------------------------------------------
# Test 7: Restoration frozen on frequency relapse below 49.85 Hz
# --------------------------------------------------------------------------
def test_staggered_restore_frozen_on_relapse():
    # Use t_stable_s=10.0 so one tick (0.5s) doesn't immediately unfreeze
    policy = StaggeredRestorationPolicy(t_stable_s=10.0, f_recovery_hz=49.95, f_freeze_hz=49.85)
    b = _make_building()
    deferred = next(a for a in b.appliances if a.priority == "deferrable")
    deferred.shed(sim_time_s=0.0)
    deferred.mark_waiting_restoration(sim_time_s=0.0)

    # First tick: above 49.95 — stable timer accumulates
    state_ok = _make_state(49.96)
    policy.tick(state_ok, [b], "incident1", 42, sim_time_s=10.0)

    # Relapse below freeze threshold
    state_bad = _make_state(49.80)
    policy.tick(state_bad, [b], "incident1", 42, sim_time_s=15.0)
    assert policy._frozen is True, "Should be frozen after relapse"

    # One tick above recovery band — stable timer only 0.5s, far below t_stable_s=10s
    state_ok2 = _make_state(49.96)
    events = policy.tick(state_ok2, [b], "incident1", 42, sim_time_s=20.0)
    restore_events = [e for e in events if e.event_type == "restore"]
    assert (
        len(restore_events) == 0
    ), "Restoration should not happen until stable timer reaches t_stable_s after freeze"
    assert policy._frozen is True, "Still frozen (stable timer only 0.5s, need 10s)"


def test_staggered_restore_uses_appliance_guarded_transition():
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        base_delay_s=0.0,
        window_s=1,
    )
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance(
                "load",
                "B1",
                "test",
                "deferrable",
                1.0,
                compressor_lockout_s=0.0,
            )
        ],
    )
    appliance = building.appliances[0]
    appliance.shed(0.0)
    appliance.mark_waiting_restoration(0.0)

    events = policy.tick(_make_state(50.0), [building], "incident", 1, 0.5)

    assert appliance.state == ApplianceState.ON
    assert [event.event_type for event in events] == ["restore"]


def test_restoration_projection_scales_with_building_weight():
    building = BuildingTwin(
        "B-weighted",
        weight_k=2,
        appliances=[
            Appliance(
                "load",
                "B-weighted",
                "test",
                "deferrable",
                0.5,
                compressor_lockout_s=0.0,
            )
        ],
    )
    appliance = building.appliances[0]
    appliance.shed(0.0)
    appliance.mark_waiting_restoration(0.0)
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.90,
        area_base_kw=10.0,
        base_delay_s=0.0,
        window_s=1,
    )

    events = policy.tick(_make_state(49.905), [building], "incident", 1, 0.5)

    assert appliance.state == ApplianceState.WAITING_RESTORATION
    assert not events


def _two_waiting_loads() -> list[BuildingTwin]:
    buildings = []
    for building_id in ("B1", "B2"):
        building = BuildingTwin(
            building_id,
            appliances=[
                Appliance(
                    "load",
                    building_id,
                    "test",
                    "deferrable",
                    0.8,
                    compressor_lockout_s=0.0,
                )
            ],
        )
        building.appliances[0].shed(0.0)
        building.appliances[0].mark_waiting_restoration(0.0)
        buildings.append(building)
    return buildings


def test_staggered_restoration_checks_cumulative_pickup():
    buildings = _two_waiting_loads()
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.99,
        H=4.0,
        area_base_kw=10.0,
        base_delay_s=0.0,
        window_s=1,
        stagger_enabled=True,
    )

    events = policy.tick(_make_state(50.0), buildings, "incident", 1, 0.5)

    assert len(events) == 1
    assert sum(
        appliance.state in {ApplianceState.ON, ApplianceState.RUNNING}
        for building in buildings
        for appliance in building.appliances
    ) == 1


def test_synchronized_restoration_progresses_one_safe_load_at_a_time():
    buildings = _two_waiting_loads()
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.99,
        H=4.0,
        area_base_kw=10.0,
        stagger_enabled=False,
    )

    events = policy.tick(
        _make_state(50.0, demand_pu=0.8), buildings, "incident", 1, 0.5
    )

    assert len(events) == 1
    assert sum(
        appliance.state == ApplianceState.ON
        for building in buildings
        for appliance in building.appliances
    ) == 1


def test_progressive_projection_accounts_for_startup_inrush():
    buildings = []
    for building_id in ("B1", "B2"):
        building = BuildingTwin(
            building_id,
            appliances=[
                Appliance(
                    "load",
                    building_id,
                    "compressor",
                    "deferrable",
                    0.4,
                    compressor_lockout_s=0.0,
                    inrush_multiplier=2.0,
                    inrush_duration_s=3.0,
                )
            ],
        )
        building.appliances[0].shed(0.0)
        building.appliances[0].mark_waiting_restoration(0.0)
        buildings.append(building)
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.99,
        H=4.0,
        area_base_kw=10.0,
        stagger_enabled=False,
    )

    events = policy.tick(
        _make_state(50.0, demand_pu=0.8), buildings, "incident", 1, 0.5
    )

    assert len(events) == 1
    assert sum(
        appliance.state in {ApplianceState.ON, ApplianceState.RUNNING}
        for building in buildings
        for appliance in building.appliances
    ) == 1


def test_progressive_restoration_does_not_wait_for_every_load_to_be_eligible():
    buildings = _two_waiting_loads()
    delayed = buildings[1].appliances[0]
    delayed.min_off_time_s = 10.0
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.90,
        area_base_kw=10.0,
        stagger_enabled=False,
    )

    events = policy.tick(
        _make_state(50.0, demand_pu=0.8), buildings, "incident", 1, 0.5
    )

    assert len(events) == 1
    assert buildings[0].appliances[0].state == ApplianceState.ON
    assert delayed.state == ApplianceState.WAITING_RESTORATION


def test_synchronized_restoration_never_reconnects_a_batch_simultaneously():
    buildings = _two_waiting_loads()
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.90,
        H=4.0,
        area_base_kw=10.0,
        stagger_enabled=False,
    )

    events = policy.tick(
        _make_state(50.0, demand_pu=0.8), buildings, "incident", 1, 0.5
    )

    assert len(events) == 1
    assert {event.simulation_time_s for event in events} == {0.5}
    assert "Synchronized progressive restore" in events[0].reason
    assert policy.tick(
        _make_state(50.0, demand_pu=0.88), buildings, "incident", 1, 1.0
    )[0].event_type == "restore"


def test_large_unsafe_pickup_does_not_block_smaller_safe_pickup():
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance("a-large", "B1", "heater", "deferrable", 4.0),
            Appliance("b-small", "B1", "fan", "deferrable", 0.5),
        ],
    )
    for appliance in building.appliances:
        appliance.shed(0.0)
        appliance.mark_waiting_restoration(0.0)
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.95,
        H=4.0,
        area_base_kw=10.0,
        base_delay_s=0.0,
        stagger_enabled=False,
    )

    events = policy.tick(
        _make_state(49.99, demand_pu=0.6), [building], "incident", 1, 1.0
    )

    assert [event.appliance_id for event in events] == ["b-small"]
    assert building.appliances[0].state == ApplianceState.WAITING_RESTORATION
    assert building.appliances[1].state == ApplianceState.ON


def test_generation_capacity_defers_unsafe_load_until_replacement_is_available():
    buildings = _two_waiting_loads()
    for building in buildings:
        building.appliances[0].rated_power_kw = 1.0
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.90,
        H=4.0,
        area_base_kw=10.0,
        up_reserve_pu=0.20,
        stagger_enabled=False,
    )

    loss_state = _make_state(
        50.0, demand_pu=0.8, generation_disturbance_pu=-0.25
    )
    first_events = policy.tick(loss_state, buildings, "incident", 1, 1.0)
    assert len(first_events) == 1
    assert first_events[0].event_type == "restore"

    remaining_state = _make_state(
        50.0, demand_pu=0.9, generation_disturbance_pu=-0.25
    )
    assert policy.tick(remaining_state, buildings, "incident", 1, 1.5) == []
    assert policy.tick(remaining_state, buildings, "incident", 1, 2.0) == []
    limited = policy.snapshot(
        remaining_state, buildings, "incident", 1
    )
    assert limited["available_generation_pu"] == pytest.approx(0.95)
    assert limited["headroom_kw"] == pytest.approx(0.5)
    assert limited["completed"] is False
    assert limited["queue"][0]["capacity_supported"] is False

    replacement_state = _make_state(50.0, demand_pu=0.9)
    final_events = policy.tick(
        replacement_state, buildings, "incident", 1, 2.5
    )
    assert len(final_events) == 1
    assert sum(
        appliance.state in {ApplianceState.ON, ApplianceState.RUNNING}
        for building in buildings
        for appliance in building.appliances
    ) == 2
    assert policy.snapshot(
        replacement_state, buildings, "incident", 1
    )["completed"] is True


def test_severe_generation_loss_progressively_restores_after_replacement():
    params = GridParams(dt_s=0.02, t_stable_s=1.0, up_reserve_pu=0.20)
    grid = GridModel(params)
    buildings = [
        BuildingTwin(
            "B0",
            appliances=[Appliance("base", "B0", "fan", "essential", 8.0)],
        )
    ]
    for building_id in ("B1", "B2"):
        appliance = Appliance(
            f"{building_id}-load",
            building_id,
            "split_ac_1ton",
            "deferrable",
            1.0,
            compressor_lockout_s=0.0,
        )
        appliance.shed(0.0)
        appliance.mark_waiting_restoration(0.0)
        buildings.append(BuildingTwin(building_id, appliances=[appliance]))
    policy = StaggeredRestorationPolicy(
        t_stable_s=params.t_stable_s,
        f_recovery_hz=params.f_recovery_hz,
        f_freeze_hz=params.f_s1_hz,
        f_safe_hz=49.90,
        H=params.H,
        area_base_kw=10.0,
        up_reserve_pu=params.up_reserve_pu,
        stagger_enabled=False,
        sample_interval_s=0.5,
    )
    state = replace(
        grid.initial_state(),
        demand_pu=0.8,
        appliance_demand_delta_pu=-0.2,
    )
    previous_demand_kw = 8.0
    agent_elapsed_s = 0.0
    restoration_start_s: float | None = None
    restoration_frequency: list[float] = []
    restore_events = []
    frequency_nadir = state.frequency_hz

    for _ in range(1500):
        for building in buildings:
            building.tick(state.time_s, params.dt_s)
        demand_kw = sum(
            appliance.current_power_kw * building.weight_k
            for building in buildings
            for appliance in building.appliances
        )
        demand_delta_pu = (demand_kw - previous_demand_kw) / 10.0
        previous_demand_kw = demand_kw
        generation_disturbance_pu = -0.25 if state.time_s < 20.0 else 0.0
        state = grid.step(
            state,
            -generation_disturbance_pu,
            demand_delta_pu,
            generation_disturbance_pu=generation_disturbance_pu,
        )
        frequency_nadir = min(frequency_nadir, state.frequency_hz)
        if restoration_start_s is not None:
            restoration_frequency.append(state.frequency_hz)
        agent_elapsed_s += params.dt_s
        if agent_elapsed_s >= 0.5 - 1e-10:
            agent_elapsed_s -= 0.5
            events = policy.tick(state, buildings, "severe-loss", 1, state.time_s)
            if events:
                assert len(events) == 1
                restore_events.extend(events)
                if restoration_start_s is None:
                    restoration_start_s = state.time_s
                    restoration_frequency.append(state.frequency_hz)

    assert len(restore_events) == 2
    assert restore_events[0].simulation_time_s < restore_events[1].simulation_time_s
    assert frequency_nadir < 49.0
    assert all(
        appliance.state == ApplianceState.ON
        for building in buildings[1:]
        for appliance in building.appliances
    )
    assert min(restoration_frequency) >= policy.f_safe_hz
    assert policy.snapshot(state, buildings, "severe-loss", 1)["completed"] is True


def test_frequency_relapse_pauses_and_resumes_restoration_without_flapping():
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance(
                "load",
                "B1",
                "split_ac_1ton",
                "deferrable",
                0.2,
                compressor_lockout_s=0.0,
            )
        ],
    )
    appliance = building.appliances[0]
    appliance.shed(0.0)
    appliance.mark_waiting_restoration(0.0)
    policy = StaggeredRestorationPolicy(
        t_stable_s=1.0,
        f_recovery_hz=49.95,
        f_freeze_hz=49.85,
        f_safe_hz=49.90,
        area_base_kw=10.0,
        base_delay_s=0.0,
        stagger_enabled=False,
    )

    assert policy.tick(_make_state(50.0), [building], "incident", 1, 0.5) == []
    assert policy.tick(_make_state(49.90), [building], "incident", 1, 1.0) == []
    assert policy.tick(_make_state(50.0), [building], "incident", 1, 1.5) == []
    restored = policy.tick(_make_state(50.0), [building], "incident", 1, 2.0)

    assert [event.event_type for event in restored] == ["restore"]
    assert appliance.state == ApplianceState.RUNNING
    assert policy.tick(_make_state(50.0), [building], "incident", 1, 2.5) == []
    assert appliance.state == ApplianceState.RUNNING


def test_critical_restoration_precedes_older_deferrable_loads():
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance("deferrable", "B1", "fan", "deferrable", 0.2),
            Appliance("medical", "B1", "medical", "critical", 0.5),
        ],
    )
    deferrable, medical = building.appliances
    for appliance in building.appliances:
        appliance.force_shed(0.0)
        appliance.mark_waiting_restoration(0.0)
    policy = StaggeredRestorationPolicy(
        t_stable_s=0.0,
        f_recovery_hz=49.90,
        f_safe_hz=49.90,
        area_base_kw=10.0,
        base_delay_s=0.0,
        stagger_enabled=False,
    )

    events = policy.tick(_make_state(50.0), [building], "incident", 1, 1.0)

    assert [event.appliance_id for event in events] == ["medical"]
    assert medical.state == ApplianceState.ON
    assert deferrable.state == ApplianceState.WAITING_RESTORATION


def test_edge_agent_transitions_to_autonomous_mode_using_sim_time():
    building = _make_building()
    agent = EdgeAgent(
        building,
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.DISTRIBUTED,
        communication_loss_grace_s=2.0,
    )

    agent.set_communication_available(False, 10.0)
    assert agent.operating_mode == OperatingMode.COMMUNICATION_DEGRADED
    agent.set_communication_available(False, 12.0)
    assert agent.operating_mode == OperatingMode.ISLANDED_AUTONOMOUS
    assert agent.should_evaluate_policy
    _, events = agent.tick(_make_state(49.0), 12.0, "incident", 42)

    assert any("shed" in event.event_type for event in events)
    assert (
        next(item for item in building.appliances if item.priority == "critical").state
        == ApplianceState.ON
    )


def test_centralized_agent_pauses_during_grace_then_fails_over_and_reconnects():
    agent = EdgeAgent(
        _make_building(),
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.CENTRALIZED,
        communication_loss_grace_s=2.0,
    )

    agent.set_communication_available(False, 10.0)
    assert agent.operating_mode == OperatingMode.COMMUNICATION_DEGRADED
    assert not agent.should_evaluate_policy
    agent.set_communication_available(False, 12.0)
    assert agent.operating_mode == OperatingMode.ISLANDED_AUTONOMOUS
    assert agent.should_evaluate_policy

    agent.set_communication_available(True, 12.5)
    assert agent.operating_mode == OperatingMode.CENTRALIZED
    assert agent.communication_available
    assert agent.should_evaluate_policy


def test_intermittent_centralized_loss_restarts_failover_grace_period():
    agent = EdgeAgent(
        _make_building(),
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.CENTRALIZED,
        communication_loss_grace_s=2.0,
    )

    agent.set_communication_available(False, 10.0)
    agent.set_communication_available(False, 11.5)
    assert not agent.should_evaluate_policy
    agent.set_communication_available(True, 11.9)
    agent.set_communication_available(False, 12.0)
    agent.set_communication_available(False, 13.9)

    assert agent.operating_mode == OperatingMode.COMMUNICATION_DEGRADED
    assert not agent.should_evaluate_policy
    agent.set_communication_available(False, 14.0)
    assert agent.operating_mode == OperatingMode.ISLANDED_AUTONOMOUS
    assert agent.should_evaluate_policy


def test_communication_degraded_agent_requires_reconnection_to_resume_dispatch():
    agent = EdgeAgent(
        _make_building(),
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.COMMUNICATION_DEGRADED,
        communication_loss_grace_s=1.0,
    )

    agent.set_communication_available(False, 10.0)
    assert not agent.should_evaluate_policy
    agent.set_communication_available(False, 20.0)
    assert agent.operating_mode == OperatingMode.COMMUNICATION_DEGRADED
    assert not agent.should_evaluate_policy
    agent.set_communication_available(True, 20.5)
    assert agent.operating_mode == OperatingMode.COMMUNICATION_DEGRADED
    assert agent.should_evaluate_policy


def test_islanded_agent_is_always_autonomous_and_never_uses_communications():
    agent = EdgeAgent(
        _make_building(),
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.ISLANDED_AUTONOMOUS,
    )

    agent.set_communication_available(True, 10.0)

    assert agent.operating_mode == OperatingMode.ISLANDED_AUTONOMOUS
    assert not agent.communication_available
    assert agent.should_evaluate_policy
