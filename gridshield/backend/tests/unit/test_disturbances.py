"""
Unit tests for the disturbance engine (Prompt 4).

Tests:
  1. GenerationLossDisturbance returns 0 before start_time_s
  2. Returns magnitude_pu during active window
  3. Returns 0 after full recovery ramp
  4. SolarSurplusDisturbance returns negative value during active window
  5. make_disturbance returns correct subclass for each type
"""

from __future__ import annotations

import pytest

from app.schemas.scenario import DisturbanceConfig
from app.twin.disturbances import (
    CombinedDisturbance,
    DemandSurgeDisturbance,
    GenerationLossDisturbance,
    SolarCloudDropDisturbance,
    SolarSurplusDisturbance,
    make_disturbance,
)


def test_generation_loss_before_start():
    d = GenerationLossDisturbance(start_time_s=10.0, magnitude_pu=0.15,
                                  duration_s=60.0, recovery_ramp_s=30.0)
    assert d.get_disturbance_pu(0.0) == 0.0
    assert d.get_disturbance_pu(9.99) == 0.0


def test_generation_loss_during_active_window():
    d = GenerationLossDisturbance(start_time_s=10.0, magnitude_pu=0.15,
                                  duration_s=60.0, recovery_ramp_s=30.0)
    assert d.get_disturbance_pu(10.0) == pytest.approx(0.15)
    assert d.get_disturbance_pu(40.0) == pytest.approx(0.15)
    assert d.get_disturbance_pu(70.0) == pytest.approx(0.15)


def test_generation_loss_after_recovery():
    d = GenerationLossDisturbance(start_time_s=10.0, magnitude_pu=0.15,
                                  duration_s=60.0, recovery_ramp_s=30.0)
    # After start(10) + duration(60) + ramp(30) = 100s
    assert d.get_disturbance_pu(100.0) == pytest.approx(0.0)
    assert d.get_disturbance_pu(200.0) == pytest.approx(0.0)


def test_solar_surplus_returns_negative():
    d = SolarSurplusDisturbance(start_time_s=5.0, magnitude_pu=0.10,
                                duration_s=120.0, recovery_ramp_s=30.0)
    val = d.get_disturbance_pu(10.0)
    assert val == pytest.approx(-0.10), f"Expected -0.10, got {val}"
    assert d.get_disturbance_pu(0.0) == 0.0


def test_make_disturbance_returns_correct_subclass():
    cfg_gen = DisturbanceConfig(type="generation_loss", start_time_s=5.0,
                                magnitude_pu=0.10, duration_s=60.0)
    assert isinstance(make_disturbance(cfg_gen, 42), GenerationLossDisturbance)

    cfg_dem = DisturbanceConfig(type="demand_surge", start_time_s=5.0,
                                magnitude_pu=0.10, duration_s=60.0)
    assert isinstance(make_disturbance(cfg_dem, 42), DemandSurgeDisturbance)

    cfg_comb = DisturbanceConfig(type="combined", start_time_s=5.0,
                                 magnitude_pu=0.10, duration_s=60.0)
    assert isinstance(make_disturbance(cfg_comb, 42), CombinedDisturbance)

    cfg_solar = DisturbanceConfig(type="solar_surplus", start_time_s=5.0,
                                  magnitude_pu=0.10, duration_s=60.0)
    assert isinstance(make_disturbance(cfg_solar, 42), SolarSurplusDisturbance)


def test_solar_cloud_drop_is_fraction_of_declared_solar_share():
    config = DisturbanceConfig(
        type="solar_cloud_drop",
        start_time_s=5.0,
        magnitude_pu=0.18,
        solar_share_pu=0.40,
        duration_s=60.0,
    )

    disturbance = make_disturbance(config)

    assert isinstance(disturbance, SolarCloudDropDisturbance)
    assert disturbance.get_disturbance_pu(10.0) == pytest.approx(0.072)
    assert disturbance.get_disturbance_components(10.0) == pytest.approx((-0.072, 0.0))


def test_solar_cloud_drop_requires_solar_share():
    with pytest.raises(ValueError, match="solar_share_pu"):
        DisturbanceConfig(
            type="solar_cloud_drop",
            start_time_s=5.0,
            magnitude_pu=0.18,
            duration_s=60.0,
        )


@pytest.mark.parametrize(
    ("disturbance_type", "expected_pu", "expected_components"),
    [
        ("generation_loss", 0.2, (-0.2, 0.0)),
        ("demand_surge", 0.2, (0.0, 0.2)),
        ("combined", 0.2, (-0.1, 0.1)),
        ("solar_surplus", -0.2, (0.2, 0.0)),
        ("solar_cloud_drop", 0.08, (-0.08, 0.0)),
    ],
)
def test_profiles_preserve_sign_magnitude_start_and_recovery(
    disturbance_type, expected_pu, expected_components
):
    config = DisturbanceConfig(
        type=disturbance_type,
        start_time_s=5,
        magnitude_pu=0.2,
        duration_s=10,
        recovery_ramp_s=10,
        solar_share_pu=0.4 if disturbance_type == "solar_cloud_drop" else None,
    )
    disturbance = make_disturbance(config, seed=123)

    assert disturbance.get_disturbance_pu(4.99) == 0
    assert disturbance.get_disturbance_components(4.99) == (0, 0)
    assert disturbance.get_disturbance_pu(5) == pytest.approx(expected_pu)
    assert disturbance.get_disturbance_components(5) == pytest.approx(
        expected_components
    )
    assert disturbance.get_disturbance_pu(15) == pytest.approx(expected_pu)
    assert disturbance.get_disturbance_pu(20) == pytest.approx(expected_pu / 2)
    assert disturbance.get_disturbance_pu(25) == 0
