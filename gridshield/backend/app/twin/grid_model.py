"""
Per-unit grid frequency model with swing equation and governor.

Implements a reduced-order single-area frequency model suitable for
studying demand-side response at area scale. Two modes are supported:

  Mode A (scaled):   quantities are per-unit of area demand; each building
                     twin represents k real buildings.
  Mode B (islanded): campus/neighbourhood islanded from the grid; building-level
                     shedding directly moves frequency.

Physics reference: framework.md §7

Equations
---------
Swing equation:     2H * d(Δω)/dt = ΔPm - ΔPL - D * Δω
Governor:           Tg * d(ΔPg)/dt = -ΔPg - (1/R) * DB(Δω)
Turbine:            Tt * d(ΔPm)/dt = ΔPg - ΔPm
Headroom clamp:     ΔPm ∈ [-down_reserve, +up_reserve]

where:
  Δω = (f - f₀) / f₀,  f₀ = 50 Hz
  f  = f₀ * (1 + Δω)
  DB(Δω) = Δω  if |Δω * f₀| > deadband_hz  else 0
  ΔP = generation_delta_pu + demand_disturbance_pu
       + appliance_demand_delta_pu - ΔPm

Numerical method: RK4 at dt_s (default 0.02 s).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.scenario import GridParams


@dataclass(frozen=True)
class GridState:
    """Immutable snapshot of the grid at one simulation time step."""

    time_s: float
    frequency_hz: float
    delta_omega: float       # per-unit frequency deviation  (f - f0) / f0
    delta_Pm: float          # mechanical power deviation (pu)
    delta_Pg: float          # governor valve/output deviation (pu)
    demand_pu: float         # total load demand (pu)
    generation_pu: float     # total generation (pu)
    disturbance_pu: float    # active disturbance magnitude (pu)
    rocof_hz_per_s: float    # rate of change of frequency (Hz/s)
    appliance_demand_delta_pu: float = 0.0
    generation_disturbance_pu: float = 0.0
    demand_disturbance_pu: float = 0.0


class GridModel:
    """
    Reduced-order single-area frequency model.

    Mode A (scaled area): quantities are per-unit of area demand.
    Mode B (islanded):    same equations, smaller H and total demand.

    step() is a pure function — no mutations, no side effects.
    """

    def __init__(
        self,
        params: GridParams,
        mode: Literal["scaled", "islanded"] = "scaled",
    ) -> None:
        self.params = params
        self.mode = mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initial_state(self) -> GridState:
        """Return a steady-state GridState at t=0, f=50 Hz, all deltas zero."""
        return GridState(
            time_s=0.0,
            frequency_hz=self.params.f0_hz,
            delta_omega=0.0,
            delta_Pm=0.0,
            delta_Pg=0.0,
            demand_pu=1.0,
            generation_pu=1.0,
            disturbance_pu=0.0,
            rocof_hz_per_s=0.0,
            appliance_demand_delta_pu=0.0,
            generation_disturbance_pu=0.0,
            demand_disturbance_pu=0.0,
        )

    def step(
        self,
        state: GridState,
        disturbance_pu: float,
        demand_delta_pu: float,
        *,
        generation_disturbance_pu: float | None = None,
        demand_disturbance_pu: float = 0.0,
    ) -> GridState:
        """
        Advance the grid model by one RK4 step.

        Pure function — takes the current state, returns the next state.
        No mutations, no global state.

        Parameters
        ----------
        state           : current GridState
        disturbance_pu  : legacy net load-imbalance input. When component values
                          are omitted, positive values mean generation loss.
        demand_delta_pu : per-unit demand change from appliance shedding/restoring
                          (-ve = load shed → frequency rises)
        generation_disturbance_pu: signed change in available generation
                                   (+ve = generation increase).
        demand_disturbance_pu: signed exogenous demand change (+ve = demand rise).
        """
        p = self.params
        dt = p.dt_s
        generation_change = (
            -disturbance_pu
            if generation_disturbance_pu is None
            else generation_disturbance_pu
        )
        net_imbalance = (
            demand_disturbance_pu
            - generation_change
            + demand_delta_pu
        )

        # Pack state variables for RK4
        y0 = (state.delta_omega, state.delta_Pg, state.delta_Pm)

        def derivatives(y: tuple[float, float, float]) -> tuple[float, float, float]:
            d_omega, d_Pg, d_Pm = y
            d_Pm_clamped = max(-p.down_reserve_pu, min(p.up_reserve_pu, d_Pm))

            # Governor deadband: DB(Δω) = 0 if |Δω * f0| <= deadband_hz
            omega_hz = d_omega * p.f0_hz
            db_input = d_omega if abs(omega_hz) > p.deadband_hz else 0.0

            d_omega_dt = (d_Pm_clamped - net_imbalance - p.D * d_omega) / (2.0 * p.H)
            d_Pg_dt = (-d_Pg - (1.0 / p.R) * db_input) / p.Tg
            d_Pm_dt = (d_Pg - d_Pm) / p.Tt

            return (d_omega_dt, d_Pg_dt, d_Pm_dt)

        # RK4 integration
        k1 = derivatives(y0)
        y1 = (y0[0] + 0.5 * dt * k1[0],
              y0[1] + 0.5 * dt * k1[1],
              y0[2] + 0.5 * dt * k1[2])

        k2 = derivatives(y1)
        y2 = (y0[0] + 0.5 * dt * k2[0],
              y0[1] + 0.5 * dt * k2[1],
              y0[2] + 0.5 * dt * k2[2])

        k3 = derivatives(y2)
        y3 = (y0[0] + dt * k3[0],
              y0[1] + dt * k3[1],
              y0[2] + dt * k3[2])

        k4 = derivatives(y3)

        new_d_omega = y0[0] + (dt / 6.0) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        new_d_Pg    = y0[1] + (dt / 6.0) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        new_d_Pm    = y0[2] + (dt / 6.0) * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])

        # Apply headroom clamp to ΔPm
        new_d_Pm = max(-p.down_reserve_pu, min(p.up_reserve_pu, new_d_Pm))

        new_freq = p.f0_hz * (1.0 + new_d_omega)
        rocof = (new_freq - state.frequency_hz) / dt

        appliance_demand_delta = state.appliance_demand_delta_pu + demand_delta_pu
        new_demand = 1.0 + appliance_demand_delta + demand_disturbance_pu
        new_gen = 1.0 + new_d_Pm + generation_change
        net_disturbance = demand_disturbance_pu - generation_change

        return GridState(
            time_s=state.time_s + dt,
            frequency_hz=new_freq,
            delta_omega=new_d_omega,
            delta_Pm=new_d_Pm,
            delta_Pg=new_d_Pg,
            demand_pu=new_demand,
            generation_pu=new_gen,
            disturbance_pu=net_disturbance,
            rocof_hz_per_s=rocof,
            appliance_demand_delta_pu=appliance_demand_delta,
            generation_disturbance_pu=generation_change,
            demand_disturbance_pu=demand_disturbance_pu,
        )

    def frequency_stage(self, state: GridState) -> str:
        """
        Classify current frequency into a named stage.

        Returns one of:
          "normal", "s0_advisory", "s1", "s2", "s3",
          "o1_absorb", "o2_absorb_plus"

        Stage boundaries from framework.md §6.3 / GridParams thresholds.
        RoCoF-based S2 trigger is included here.
        """
        p = self.params
        f = state.frequency_hz
        rocof = state.rocof_hz_per_s

        if f <= p.f_s3_hz:
            return "s3"
        if f <= p.f_s2_hz or rocof <= p.rocof_s2_threshold:
            return "s2"
        if f <= p.f_s1_hz:
            return "s1"
        if f <= p.f_s0_hz:
            return "s0_advisory"
        if f >= p.f_o2_hz:
            return "o2_absorb_plus"
        if f >= p.f_o1_hz:
            return "o1_absorb"
        return "normal"
