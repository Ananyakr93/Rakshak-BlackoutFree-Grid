"""
Unit tests for the GridModel (Prompt 3).

Tests:
  1. No disturbance → frequency stays 50.0 ± 1e-6 Hz
  2. Generation loss → frequency falls below 49.9 Hz within 10 s
  3. Demand reduction → frequency rises or stabilises vs uncontrolled
  4. Governor deadband → delta_Pg stays zero for small disturbance
  5. Headroom saturation → delta_Pm never exceeds up_reserve_pu
  6. RK4 convergence → dt=0.01 vs dt=0.02 difference < 0.01 Hz
  7. Stage classification → correct labels for specific frequency values
"""

from __future__ import annotations

import pytest

from app.schemas.scenario import GridParams
from app.twin.grid_model import GridModel, GridState


def _default_params(**overrides) -> GridParams:
    return GridParams(**overrides)


def _run(model: GridModel, steps: int, disturbance: float = 0.0, demand_delta: float = 0.0) -> GridState:
    state = model.initial_state()
    for _ in range(steps):
        state = model.step(state, disturbance, demand_delta)
    return state


# --------------------------------------------------------------------------
# Test 1: No disturbance — frequency constant at 50.0 Hz
# --------------------------------------------------------------------------
def test_no_disturbance_frequency_stable():
    params = _default_params()
    model = GridModel(params, mode="scaled")
    steps = int(300.0 / params.dt_s)  # 300 seconds
    state = _run(model, steps, disturbance=0.0, demand_delta=0.0)
    assert abs(state.frequency_hz - 50.0) < 1e-6, (
        f"Expected 50.0 Hz, got {state.frequency_hz}"
    )


# --------------------------------------------------------------------------
# Test 2: Generation loss → frequency falls below 49.9 Hz within 10 s
# --------------------------------------------------------------------------
def test_generation_loss_frequency_falls():
    params = _default_params()
    model = GridModel(params, mode="scaled")
    state = model.initial_state()
    steps_10s = int(10.0 / params.dt_s)

    min_freq = 50.0
    for _ in range(steps_10s):
        state = model.step(state, disturbance_pu=0.10, demand_delta_pu=0.0)
        min_freq = min(min_freq, state.frequency_hz)

    assert min_freq < 49.9, (
        f"Expected frequency to fall below 49.9 Hz, got min={min_freq:.4f} Hz"
    )


# --------------------------------------------------------------------------
# Test 3: Demand reduction → frequency rises vs uncontrolled trajectory
# --------------------------------------------------------------------------
def test_demand_reduction_frequency_improves():
    params = _default_params()
    model = GridModel(params, mode="scaled")
    steps = int(30.0 / params.dt_s)

    # Uncontrolled: 10% disturbance, no shedding
    state_uncontrolled = model.initial_state()
    for _ in range(steps):
        state_uncontrolled = model.step(state_uncontrolled, 0.10, 0.0)

    # Controlled: same disturbance + 5% demand shed
    state_controlled = model.initial_state()
    for _ in range(steps):
        state_controlled = model.step(state_controlled, 0.10, -0.05)

    assert state_controlled.frequency_hz > state_uncontrolled.frequency_hz, (
        f"Controlled ({state_controlled.frequency_hz:.4f}) should be > "
        f"uncontrolled ({state_uncontrolled.frequency_hz:.4f})"
    )


def test_telemetry_quantities_include_disturbance_and_appliance_components():
    model = GridModel(_default_params())
    state = model.step(
        model.initial_state(),
        disturbance_pu=0.0,
        demand_delta_pu=-0.05,
        generation_disturbance_pu=-0.10,
        demand_disturbance_pu=0.03,
    )

    assert state.generation_pu == pytest.approx(0.90 + state.delta_Pm)
    assert state.demand_pu == pytest.approx(0.98)
    assert state.generation_disturbance_pu == pytest.approx(-0.10)
    assert state.demand_disturbance_pu == pytest.approx(0.03)
    assert state.disturbance_pu == pytest.approx(0.13)


# --------------------------------------------------------------------------
# Test 4: Governor deadband — delta_Pg stays ~zero for tiny disturbance
# --------------------------------------------------------------------------
def test_governor_deadband():
    params = _default_params()
    model = GridModel(params, mode="scaled")
    state = model.initial_state()

    # Tiny disturbance that keeps f deviation within ±0.03 Hz deadband:
    # 0.03 Hz / 50 Hz = 0.0006 pu deviation; use a disturbance that causes less
    tiny = 0.0002  # very small disturbance, stays inside deadband
    for i in range(20):
        state = model.step(state, disturbance_pu=tiny, demand_delta_pu=0.0)
        if i < 20:
            assert abs(state.delta_Pg) < 1e-9, (
                f"delta_Pg should be zero inside deadband at step {i}, got {state.delta_Pg}"
            )


# --------------------------------------------------------------------------
# Test 5: Headroom saturation — delta_Pm never exceeds up_reserve_pu
# --------------------------------------------------------------------------
def test_headroom_saturation():
    params = _default_params()
    model = GridModel(params, mode="scaled")
    state = model.initial_state()
    steps = int(60.0 / params.dt_s)

    for _ in range(steps):
        state = model.step(state, disturbance_pu=0.5, demand_delta_pu=0.0)
        assert state.delta_Pm <= params.up_reserve_pu + 1e-9, (
            f"delta_Pm {state.delta_Pm} exceeded up_reserve {params.up_reserve_pu}"
        )
        assert state.delta_Pm >= -params.down_reserve_pu - 1e-9, (
            f"delta_Pm {state.delta_Pm} below -down_reserve {-params.down_reserve_pu}"
        )


# --------------------------------------------------------------------------
# Test 6: RK4 convergence — dt=0.01 vs dt=0.02 difference < 0.01 Hz
# --------------------------------------------------------------------------
def test_rk4_convergence():
    params_coarse = _default_params(dt_s=0.02)
    params_fine   = _default_params(dt_s=0.01)

    model_coarse = GridModel(params_coarse, mode="scaled")
    model_fine   = GridModel(params_fine, mode="scaled")

    duration_s = 60.0

    state_c = model_coarse.initial_state()
    for _ in range(int(duration_s / params_coarse.dt_s)):
        state_c = model_coarse.step(state_c, 0.10, 0.0)

    state_f = model_fine.initial_state()
    for _ in range(int(duration_s / params_fine.dt_s)):
        state_f = model_fine.step(state_f, 0.10, 0.0)

    diff = abs(state_c.frequency_hz - state_f.frequency_hz)
    assert diff < 0.01, f"RK4 convergence gap {diff:.5f} Hz exceeds 0.01 Hz"


# --------------------------------------------------------------------------
# Test 7: Stage classification
# --------------------------------------------------------------------------
@pytest.mark.parametrize("freq_hz, expected_stage", [
    (49.39, "s3"),
    (49.59, "s2"),
    (49.84, "s1"),
    (49.89, "s0_advisory"),
    (50.04, "normal"),
    (50.21, "o2_absorb_plus"),
])
def test_stage_classification(freq_hz: float, expected_stage: str):
    params = _default_params()
    model = GridModel(params, mode="scaled")
    # Build a state with the desired frequency
    delta_omega = (freq_hz - params.f0_hz) / params.f0_hz
    state = GridState(
        time_s=0.0,
        frequency_hz=freq_hz,
        delta_omega=delta_omega,
        delta_Pm=0.0,
        delta_Pg=0.0,
        demand_pu=1.0,
        generation_pu=1.0,
        disturbance_pu=0.0,
        rocof_hz_per_s=0.0,
    )
    stage = model.frequency_stage(state)
    assert stage == expected_stage, (
        f"f={freq_hz} Hz: expected '{expected_stage}', got '{stage}'"
    )
