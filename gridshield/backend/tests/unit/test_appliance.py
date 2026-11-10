"""
Unit tests for Appliance state machine and BuildingTwin (Prompt 5).

Tests:
  1. Shedding critical appliance does nothing
  2. Shedding deferrable ON appliance → SHED, negative delta
  3. Cannot shed an already SHED appliance
  4. min_on_time_s lockout blocks early shed
  5. Restore WAITING_RESTORATION → ON, positive delta
  6. max_shed_minutes: is_shed_too_long() returns True at correct sim time
  7. BuildingTwin.total_demand_kw equals sum of current_power_kw after shedding two appliances
"""

from __future__ import annotations

import pytest

from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin


def _make_appliance(
    priority="deferrable",
    rated_power_kw=1.0,
    min_on_time_s=0.0,
    min_off_time_s=0.0,
    max_shed_minutes=None,
    enrolled=True,
    initial_state=ApplianceState.ON,
    initial_sim_time_s=0.0,
) -> Appliance:
    return Appliance(
        appliance_id="test_appl",
        building_id="B1",
        appliance_type="test",
        priority=priority,
        rated_power_kw=rated_power_kw,
        min_on_time_s=min_on_time_s,
        min_off_time_s=min_off_time_s,
        max_shed_minutes=max_shed_minutes,
        enrolled=enrolled,
        initial_state=initial_state,
        initial_sim_time_s=initial_sim_time_s,
    )


# --------------------------------------------------------------------------
# Test 1: Critical appliance cannot be shed
# --------------------------------------------------------------------------
def test_shed_critical_appliance_is_noop():
    a = _make_appliance(priority="critical", rated_power_kw=0.5)
    delta = a.shed(sim_time_s=10.0)
    assert delta == 0.0
    assert a.state == ApplianceState.ON
    assert a.current_power_kw == 0.5


# --------------------------------------------------------------------------
# Test 2: Shedding deferrable ON appliance → SHED, negative delta
# --------------------------------------------------------------------------
def test_shed_deferrable_on_appliance():
    a = _make_appliance(priority="deferrable", rated_power_kw=2.0)
    delta = a.shed(sim_time_s=10.0)
    assert delta == pytest.approx(-2.0)
    assert a.state == ApplianceState.SHED
    assert a.current_power_kw == 0.0


# --------------------------------------------------------------------------
# Test 3: Cannot shed an already SHED appliance
# --------------------------------------------------------------------------
def test_cannot_shed_already_shed():
    a = _make_appliance(priority="deferrable", rated_power_kw=1.0)
    a.shed(sim_time_s=10.0)
    delta2 = a.shed(sim_time_s=11.0)
    assert delta2 == 0.0
    assert a.state == ApplianceState.SHED


# --------------------------------------------------------------------------
# Test 4: min_on_time_s lockout — shed blocked before min on time elapsed
# --------------------------------------------------------------------------
def test_min_on_time_lockout():
    # Appliance turned on at t=0; min_on_time=120s
    a = _make_appliance(
        priority="deferrable", rated_power_kw=1.0, min_on_time_s=120.0, initial_sim_time_s=0.0
    )
    # Try to shed at t=60 (before 120s min on time)
    delta = a.shed(sim_time_s=60.0)
    assert delta == 0.0, "Should be blocked by min_on_time_s"
    assert a.state == ApplianceState.ON

    # Shed at t=130 (after 120s)
    delta2 = a.shed(sim_time_s=130.0)
    assert delta2 == pytest.approx(-1.0)
    assert a.state == ApplianceState.SHED


# --------------------------------------------------------------------------
# Test 5: Restore WAITING_RESTORATION → ON, positive delta
# --------------------------------------------------------------------------
def test_restore_waiting_restoration():
    a = _make_appliance(priority="deferrable", rated_power_kw=1.5, min_off_time_s=0.0)
    a.shed(sim_time_s=10.0)
    a.mark_waiting_restoration(sim_time_s=20.0)
    assert a.state == ApplianceState.WAITING_RESTORATION

    delta = a.restore(sim_time_s=25.0)
    assert delta == pytest.approx(1.5)
    assert a.state == ApplianceState.ON
    assert a.current_power_kw == pytest.approx(1.5)


# --------------------------------------------------------------------------
# Test 6: max_shed_minutes — is_shed_too_long returns True at correct time
# --------------------------------------------------------------------------
def test_max_shed_minutes_exceeded():
    # max_shed_minutes=0.5 → 30 seconds
    a = _make_appliance(priority="deferrable", rated_power_kw=1.0, max_shed_minutes=0.5)
    a.shed(sim_time_s=100.0)
    assert not a.is_shed_too_long(sim_time_s=110.0)  # 10s < 30s
    assert not a.is_shed_too_long(sim_time_s=129.9)  # 29.9s < 30s
    assert a.is_shed_too_long(sim_time_s=131.0)  # 31s > 30s


# --------------------------------------------------------------------------
# Test 7: BuildingTwin.total_demand_kw equals sum after shedding two appliances
# --------------------------------------------------------------------------
def test_building_twin_demand_after_shed():
    a1 = _make_appliance(priority="deferrable", rated_power_kw=2.0)
    a1.appliance_id = "A1"
    a2 = _make_appliance(priority="essential", rated_power_kw=1.0)
    a2.appliance_id = "A2"
    a3 = _make_appliance(priority="critical", rated_power_kw=0.5)
    a3.appliance_id = "A3"

    b = BuildingTwin(building_id="B1", weight_k=1, appliances=[a1, a2, a3])

    # Initial: all ON
    assert b.total_demand_kw == pytest.approx(3.5)

    # Shed A1 (deferrable)
    a1.shed(sim_time_s=10.0)
    b.apply_demand_delta()
    assert b.total_demand_kw == pytest.approx(1.5)

    # Shed A2 (essential) — force shed by temporarily setting min_on_time_s=0
    a2.shed(sim_time_s=10.0)
    b.apply_demand_delta()
    # A3 (critical) should never be shed; total = 0.5
    assert b.total_demand_kw == pytest.approx(0.5)

    # Critical load still on
    assert a3.state == ApplianceState.ON
    assert a3.current_power_kw == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Test: apply_demand_delta returns 0.0 when no state changes
# --------------------------------------------------------------------------
def test_building_twin_no_change_returns_zero():
    a1 = _make_appliance(rated_power_kw=1.0)
    b = BuildingTwin(building_id="B1", appliances=[a1])
    delta = b.apply_demand_delta()
    assert delta == pytest.approx(0.0)


def test_compressor_restart_lockout_uses_simulation_time():
    appliance = Appliance(
        "ac",
        "B1",
        "split_ac_1ton",
        "deferrable",
        1.0,
        min_off_time_s=2.0,
        compressor_lockout_s=10.0,
    )
    appliance.shed(5.0)
    appliance.mark_waiting_restoration(6.0)
    assert appliance.state == ApplianceState.LOCKED_OUT
    assert appliance.restore(14.99) == 0.0
    assert appliance.state == ApplianceState.LOCKED_OUT

    appliance.tick(15.0)
    assert appliance.state == ApplianceState.WAITING_RESTORATION
    assert appliance.restore(15.0) == pytest.approx(3.0)
    assert appliance.state == ApplianceState.RUNNING


def test_startup_transient_is_appliance_specific_and_simulation_timed():
    ac = Appliance(
        "ac",
        "B1",
        "split_ac_1ton",
        "deferrable",
        1.0,
        initial_state=ApplianceState.OFF,
        inrush_multiplier=4.0,
        inrush_duration_s=2.0,
    )
    heater = Appliance(
        "heater",
        "B1",
        "geyser_15l",
        "deferrable",
        2.0,
        initial_state=ApplianceState.OFF,
    )
    assert ac.start_from_off(10.0) == pytest.approx(4.0)
    assert heater.start_from_off(10.0) == pytest.approx(2.0)
    ac.tick(11.0)
    assert ac.current_power_kw == pytest.approx(2.5)
    ac.tick(12.0)
    assert ac.current_power_kw == pytest.approx(1.0)
    assert ac.state == ApplianceState.ON


def test_appliance_timer_reset_is_fresh_for_new_scenario():
    first_run = _make_appliance(
        min_on_time_s=20.0,
        initial_sim_time_s=100.0,
    )
    assert first_run.shed(105.0) == 0.0

    second_run = _make_appliance(
        min_on_time_s=20.0,
        initial_sim_time_s=0.0,
    )
    assert second_run.shed(20.0) == pytest.approx(-1.0)


def test_short_startup_transient_is_averaged_over_grid_step():
    appliance = Appliance(
        "pump",
        "B1",
        "water_pump",
        "essential",
        1.0,
        initial_state=ApplianceState.OFF,
        inrush_multiplier=3.0,
        inrush_duration_s=0.5,
    )
    appliance.start_from_off(0.0)

    appliance.tick(0.0, dt_s=1.0)

    assert appliance.current_power_kw == pytest.approx(1.5)
    assert appliance.state == ApplianceState.ON
