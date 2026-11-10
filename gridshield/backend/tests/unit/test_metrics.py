"""
Unit tests for evaluation metrics (Prompt 8).

Tests:
  1. frequency_nadir returns correct minimum
  2. jains_fairness_index returns 1.0 for equal, <1.0 for unequal
  3. critical_energy_not_served_kwh returns 0 when no critical shed events
  4. recovery_time_s returns None when frequency never recovers
  5. energy_curtailed_by_tier correctly separates events by priority
"""

from __future__ import annotations

import uuid

import pytest

from app.evaluation.metrics import (
    critical_energy_not_served_kwh,
    energy_curtailed_by_tier,
    frequency_nadir,
    jains_fairness_index,
    medical_load_interruption_s,
    recovery_time_s,
)
from app.schemas.events import ControlEvent
from app.schemas.scenario import (
    ApplianceConfig,
    BuildingConfig,
    DisturbanceConfig,
    ScenarioConfig,
)
from app.schemas.telemetry import TelemetrySample

_RUN_ID = uuid.uuid4()


def _sample(t: float, f: float) -> TelemetrySample:
    return TelemetrySample(
        run_id=_RUN_ID,
        simulation_time_s=t,
        frequency_hz=f,
        generation_pu=1.0,
        demand_pu=1.0,
        frequency_stage="normal",
        rocof_hz_per_s=0.0,
        sequence_number=int(t * 2),
    )


def _event(
    event_type: str,
    priority: str,
    appliance_id: str | None = None,
    time_s: float = 10.0,
) -> ControlEvent:
    return ControlEvent(
        run_id=_RUN_ID,
        simulation_time_s=time_s,
        event_type=event_type,
        building_id="B1",
        appliance_id=appliance_id,
        reason="test",
        frequency_hz=49.8,
        priority=priority,
    )


def _scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="metric fixture",
        seed=1,
        simulation_duration_s=7200,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=1,
            magnitude_pu=0.1,
            duration_s=10,
        ),
        buildings=[
            BuildingConfig(
                building_id="B1",
                appliances=[
                    ApplianceConfig(
                        appliance_id="medical",
                        appliance_type="medical_device",
                        priority="critical",
                        rated_power_kw=0.5,
                    ),
                    ApplianceConfig(
                        appliance_id="deferrable-1",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                    ),
                    ApplianceConfig(
                        appliance_id="deferrable-2",
                        appliance_type="geyser_15l",
                        priority="deferrable",
                        rated_power_kw=2.0,
                    ),
                    ApplianceConfig(
                        appliance_id="essential",
                        appliance_type="refrigerator",
                        priority="essential",
                        rated_power_kw=0.5,
                    ),
                ],
            )
        ],
    )


# --------------------------------------------------------------------------
# Test 1: frequency_nadir returns correct minimum
# --------------------------------------------------------------------------
def test_frequency_nadir():
    samples = [_sample(t, f) for t, f in [(0, 50.0), (5, 49.6), (10, 49.3), (15, 49.5)]]
    assert frequency_nadir(samples) == pytest.approx(49.3)


def test_frequency_nadir_empty():
    assert frequency_nadir([]) == pytest.approx(50.0)


# --------------------------------------------------------------------------
# Test 2: jains_fairness_index
# --------------------------------------------------------------------------
def test_jains_fairness_equal_curtailments():
    curtailments = {"B1": 1.0, "B2": 1.0, "B3": 1.0}
    assert jains_fairness_index(curtailments) == pytest.approx(1.0)


def test_jains_fairness_unequal_curtailments():
    curtailments = {"B1": 3.0, "B2": 0.0, "B3": 0.0}
    idx = jains_fairness_index(curtailments)
    assert idx < 1.0, f"Unequal curtailments should give J < 1.0, got {idx}"


def test_jains_fairness_all_zero():
    curtailments = {"B1": 0.0, "B2": 0.0}
    assert jains_fairness_index(curtailments) == pytest.approx(1.0)


def test_jains_fairness_empty():
    assert jains_fairness_index({}) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Test 3: critical_energy_not_served_kwh returns 0 when no critical sheds
# --------------------------------------------------------------------------
def test_critical_ens_no_shed_events():
    events = [
        _event("shed_deferrable", "deferrable", "deferrable-1"),
        _event("restore", "deferrable", "deferrable-1"),
    ]
    assert critical_energy_not_served_kwh(events, _scenario(), 100.0) == 0.0


def test_critical_ens_with_critical_shed():
    events = [
        _event("feeder_trip", "critical", "medical", 10.0),
        _event("restore", "critical", "medical", 70.0),
    ]
    assert critical_energy_not_served_kwh(events, _scenario(), 100.0) == pytest.approx(
        0.5 * 60 / 3600
    )


def test_medical_load_interruption_integrates_only_medical_devices():
    events = [
        _event("feeder_trip", "critical", "medical", 10.0),
        _event("shed_deferrable", "deferrable", "deferrable-1", 15.0),
        _event("restore", "critical", "medical", 70.0),
        _event("restore", "deferrable", "deferrable-1", 90.0),
    ]

    assert medical_load_interruption_s(events, _scenario(), 100.0) == pytest.approx(60.0)


# --------------------------------------------------------------------------
# Test 4: recovery_time_s returns None when frequency never recovers
# --------------------------------------------------------------------------
def test_recovery_time_never_recovers():
    # Frequency stays below 49.95 Hz throughout
    samples = [_sample(t, 49.6) for t in range(300)]
    result = recovery_time_s(samples, recovery_band_hz=49.95, stability_duration_s=60.0)
    assert result is None


def test_recovery_time_recovers():
    # Disturbance at t=10, recovery at t=100 staying at 49.96 for 60s
    samples = (
        [_sample(t, 50.0) for t in range(0, 10)]
        + [_sample(t, 49.6) for t in range(10, 100)]
        + [_sample(t, 49.96) for t in range(100, 180)]
    )
    result = recovery_time_s(samples, recovery_band_hz=49.95, stability_duration_s=60.0,
                             disturbance_start_s=10.0)
    assert result is not None
    assert result >= 60.0


# --------------------------------------------------------------------------
# Test 5: energy_curtailed_by_tier correctly separates by priority
# --------------------------------------------------------------------------
def test_energy_curtailed_by_tier():
    events = [
        _event("shed_deferrable", "deferrable", "deferrable-1", 10.0),
        _event("shed_deferrable", "deferrable", "deferrable-2", 10.0),
        _event("shed_essential", "essential", "essential", 10.0),
        _event("restore", "deferrable", "deferrable-1", 3610.0),
        _event("restore", "deferrable", "deferrable-2", 3610.0),
        _event("restore", "essential", "essential", 3610.0),
    ]
    tiers = energy_curtailed_by_tier(events, _scenario(), 3610.0)
    assert tiers["deferrable"] == pytest.approx(3.0)
    assert tiers["essential"] == pytest.approx(0.5)
    assert tiers["critical"] == pytest.approx(0.0)
