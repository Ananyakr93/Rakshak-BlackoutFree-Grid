"""
Appliance state machine for GridShield.

Models a single virtual appliance with priority-aware shedding and
staggered restoration. Enforces min on/off times, critical-load protection,
and max shed duration limits. Every state transition updates current_power_kw
atomically so the building demand total is always consistent.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Literal


class ApplianceState(str, Enum):
    OFF = "OFF"
    ON = "ON"
    SHED = "SHED"
    WAITING_RESTORATION = "WAITING_RESTORATION"
    LOCKED_OUT = "LOCKED_OUT"  # min on/off time not yet satisfied
    RUNNING = "RUNNING"  # startup transient is active
    UNAVAILABLE = "UNAVAILABLE"  # fault or unknown


class Appliance:
    """
    Virtual appliance with priority, state machine, and power tracking.

    Rules enforced here (not just in policy layer):
      - Critical appliances: shed() always no-ops and returns 0.0
      - min_on_time_s: shed blocked if ON for less than this duration
      - min_off_time_s: restore blocked if in SHED/WAITING less than this
      - max_shed_minutes: is_shed_too_long() returns True past this limit
      - State changes atomically update current_power_kw
    """

    def __init__(
        self,
        appliance_id: str,
        building_id: str,
        appliance_type: str,
        priority: Literal["critical", "essential", "deferrable"],
        rated_power_kw: float,
        min_on_time_s: float = 0.0,
        min_off_time_s: float = 0.0,
        max_shed_minutes: float | None = None,
        enrolled: bool = True,
        initial_state: ApplianceState = ApplianceState.ON,
        initial_sim_time_s: float = 0.0,
        compressor_lockout_s: float | None = None,
        inrush_multiplier: float | None = None,
        inrush_duration_s: float | None = None,
        startup_recovery_profile: Literal["linear", "exponential"] = "linear",
    ) -> None:
        self.appliance_id = appliance_id
        self.building_id = building_id
        self.appliance_type = appliance_type
        self.priority = priority
        self.rated_power_kw = rated_power_kw
        self.min_on_time_s = min_on_time_s
        self.min_off_time_s = min_off_time_s
        self.max_shed_minutes = max_shed_minutes
        self.enrolled = enrolled
        is_compressor = appliance_type.startswith(("split_ac_", "refrigerator"))
        self.compressor_lockout_s = (
            compressor_lockout_s
            if compressor_lockout_s is not None
            else (180.0 if is_compressor else 0.0)
        )
        self.inrush_multiplier = (
            inrush_multiplier
            if inrush_multiplier is not None
            else self._default_inrush_multiplier(appliance_type)
        )
        self.inrush_duration_s = (
            inrush_duration_s
            if inrush_duration_s is not None
            else self._default_inrush_duration(appliance_type)
        )
        self.startup_recovery_profile = startup_recovery_profile

        # Runtime state
        self.state: ApplianceState = initial_state
        self._power_limit_fraction = 1.0
        self.last_state_change_s: float = initial_sim_time_s
        self._lockout_until_s = initial_sim_time_s
        self._restore_pending = False
        self._start_pending = False
        self._startup_started_s: float | None = None
        self.current_power_kw: float = rated_power_kw if initial_state == ApplianceState.ON else 0.0

    @staticmethod
    def _default_inrush_multiplier(appliance_type: str) -> float:
        if appliance_type.startswith("split_ac_"):
            return 3.0
        if appliance_type == "refrigerator":
            return 2.0
        if appliance_type == "water_pump":
            return 2.0
        return 1.0

    @staticmethod
    def _default_inrush_duration(appliance_type: str) -> float:
        if appliance_type.startswith("split_ac_"):
            return 1.0
        if appliance_type == "refrigerator":
            return 0.5
        if appliance_type == "water_pump":
            return 0.5
        return 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def shed(self, sim_time_s: float) -> float:
        """
        Attempt to shed this appliance.

        Returns demand delta kW (negative = load removed).
        Returns 0.0 (no-op) if:
          - priority is 'critical'
          - not enrolled
          - state is not ON or RUNNING
          - min_on_time_s not yet elapsed since the last start transition
        """
        if self.priority == "critical":
            return 0.0
        if not self.enrolled:
            return 0.0
        if self.state not in (ApplianceState.ON, ApplianceState.RUNNING):
            return 0.0
        if sim_time_s - self.last_state_change_s < self.min_on_time_s:
            return 0.0

        return self._shed_transition(sim_time_s)

    def force_shed(self, sim_time_s: float) -> float:
        """Trip a physical feeder while retaining appliance restart protection."""
        if self.state not in (ApplianceState.ON, ApplianceState.RUNNING):
            return 0.0
        return self._shed_transition(sim_time_s)

    def _shed_transition(self, sim_time_s: float) -> float:
        old_power = self.current_power_kw
        self.state = ApplianceState.SHED
        self._power_limit_fraction = 1.0
        self.last_state_change_s = sim_time_s
        self._lockout_until_s = max(self._lockout_until_s, sim_time_s + self.compressor_lockout_s)
        self._restore_pending = False
        self._start_pending = False
        self._startup_started_s = None
        self.current_power_kw = 0.0
        return -old_power  # negative delta

    def set_power_limit_fraction(self, fraction: float, sim_time_s: float) -> float:
        """Set a persistent operating limit and return the immediate power delta."""
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise ValueError("power limit fraction must be between 0 and 1")
        if fraction == self._power_limit_fraction:
            return 0.0
        previous_power = self.current_power_kw
        self._power_limit_fraction = fraction
        if self.state == ApplianceState.ON:
            self.current_power_kw = self.rated_power_kw * fraction
        elif self.state == ApplianceState.RUNNING:
            self.current_power_kw = self._power_at(sim_time_s)
        return self.current_power_kw - previous_power

    def restore(self, sim_time_s: float) -> float:
        """
        Attempt to restore this appliance.

        Returns demand delta kW (positive = load added).
        Returns 0.0 (no-op) if:
          - state is not WAITING_RESTORATION
          - min_off_time_s not yet elapsed since shed/waiting
        """
        if self.state not in (
            ApplianceState.WAITING_RESTORATION,
            ApplianceState.LOCKED_OUT,
        ):
            return 0.0
        off_until = max(
            self.last_state_change_s + self.min_off_time_s,
            self._lockout_until_s,
        )
        if sim_time_s < off_until:
            self.state = ApplianceState.LOCKED_OUT
            self._restore_pending = True
            return 0.0

        self._start(sim_time_s)
        return self.current_power_kw

    def _start(self, sim_time_s: float) -> None:
        self.state = ApplianceState.RUNNING if self.inrush_duration_s > 0 else ApplianceState.ON
        self.last_state_change_s = sim_time_s
        self._startup_started_s = sim_time_s if self.inrush_duration_s > 0 else None
        self._restore_pending = False
        self._start_pending = False
        self.current_power_kw = self._power_at(sim_time_s)

    def start_from_off(self, sim_time_s: float) -> float:
        """Start an OFF appliance, respecting its minimum-OFF timer."""
        if self.state != ApplianceState.OFF:
            return 0.0
        if sim_time_s < self.last_state_change_s + self.min_off_time_s:
            self.state = ApplianceState.LOCKED_OUT
            self._start_pending = True
            return 0.0
        self._start(sim_time_s)
        return self.current_power_kw

    def mark_waiting_restoration(self, sim_time_s: float) -> None:
        """Transition SHED → WAITING_RESTORATION."""
        if self.state == ApplianceState.SHED:
            if sim_time_s < self._lockout_until_s:
                self.state = ApplianceState.LOCKED_OUT
            else:
                self.state = ApplianceState.WAITING_RESTORATION
            self._restore_pending = True

    def can_shed(self, sim_time_s: float) -> bool:
        """True if this appliance is eligible to be shed right now."""
        if self.priority == "critical":
            return False
        if not self.enrolled:
            return False
        if self.state not in (ApplianceState.ON, ApplianceState.RUNNING):
            return False
        if sim_time_s - self.last_state_change_s < self.min_on_time_s:
            return False
        return True

    def can_restore(self, sim_time_s: float) -> bool:
        """True when this appliance is waiting and all simulation-time guards pass."""
        return self.state == ApplianceState.WAITING_RESTORATION and sim_time_s >= max(
            self.last_state_change_s + self.min_off_time_s,
            self._lockout_until_s,
        )

    def lockout_remaining_s(self, sim_time_s: float) -> float:
        """Return the remaining simulation-time restart guard."""
        if self.state not in (
            ApplianceState.SHED,
            ApplianceState.LOCKED_OUT,
            ApplianceState.WAITING_RESTORATION,
        ):
            return 0.0
        deadline = max(
            self.last_state_change_s + self.min_off_time_s,
            self._lockout_until_s,
        )
        return max(0.0, deadline - sim_time_s)

    @property
    def restoration_pending(self) -> bool:
        """Whether the appliance is waiting for a guarded restoration transition."""
        return self._restore_pending

    def is_shed_too_long(self, sim_time_s: float) -> bool:
        """
        True if the appliance has been shed longer than max_shed_minutes.
        Only relevant if max_shed_minutes is set and state is SHED/WAITING.
        """
        if self.max_shed_minutes is None:
            return False
        if self.state not in (
            ApplianceState.SHED,
            ApplianceState.WAITING_RESTORATION,
            ApplianceState.LOCKED_OUT,
        ):
            return False
        shed_duration_s = sim_time_s - self.last_state_change_s
        return shed_duration_s > self.max_shed_minutes * 60.0

    def tick(self, sim_time_s: float, dt_s: float = 0.0) -> None:
        """Advance lockout and startup transients using simulation time only."""
        if self.state == ApplianceState.WAITING_RESTORATION and sim_time_s < max(
            self._lockout_until_s,
            self.last_state_change_s + self.min_off_time_s,
        ):
            self.state = ApplianceState.LOCKED_OUT
            self._restore_pending = True
        if self.state == ApplianceState.LOCKED_OUT and sim_time_s >= max(
            self._lockout_until_s, self.last_state_change_s + self.min_off_time_s
        ):
            if self._start_pending:
                self._start(sim_time_s)
            else:
                self.state = ApplianceState.WAITING_RESTORATION
        if self.state == ApplianceState.RUNNING:
            self.current_power_kw = (
                self._average_power(sim_time_s, dt_s)
                if dt_s > 0
                else self._power_at(sim_time_s)
            )
            if (
                self._startup_started_s is not None
                and sim_time_s + dt_s - self._startup_started_s >= self.inrush_duration_s
            ):
                self.state = ApplianceState.ON
                self._startup_started_s = None
        elif self.state == ApplianceState.ON:
            self.current_power_kw = self.rated_power_kw * self._power_limit_fraction

    def _power_at(self, sim_time_s: float) -> float:
        if self._startup_started_s is None or self.inrush_duration_s <= 0:
            return self.rated_power_kw * self._power_limit_fraction
        elapsed = max(0.0, sim_time_s - self._startup_started_s)
        if elapsed >= self.inrush_duration_s:
            return self.rated_power_kw
        excess = self.rated_power_kw * (self.inrush_multiplier - 1.0)
        progress = elapsed / self.inrush_duration_s
        if self.startup_recovery_profile == "exponential":
            progress = (1.0 - math.exp(-5.0 * progress)) / (1.0 - math.exp(-5.0))
        return (
            self.rated_power_kw + excess * (1.0 - progress)
        ) * self._power_limit_fraction

    def _average_power(self, sim_time_s: float, dt_s: float) -> float:
        """Average startup demand over one grid step to preserve transient energy."""
        if self._startup_started_s is None or self.inrush_duration_s <= 0:
            return self.rated_power_kw * self._power_limit_fraction
        elapsed_start = max(0.0, sim_time_s - self._startup_started_s)
        elapsed_end = min(
            self.inrush_duration_s,
            sim_time_s + dt_s - self._startup_started_s,
        )
        if elapsed_end <= elapsed_start:
            return self.rated_power_kw * self._power_limit_fraction
        excess = self.rated_power_kw * (self.inrush_multiplier - 1.0)
        duration = self.inrush_duration_s
        if self.startup_recovery_profile == "exponential":
            normalizer = 1.0 - math.exp(-5.0)
            integral = (
                duration / 5.0
                * (math.exp(-5.0 * elapsed_start / duration)
                   - math.exp(-5.0 * elapsed_end / duration))
                - math.exp(-5.0) * (elapsed_end - elapsed_start)
            ) / normalizer
        else:
            integral = (
                elapsed_end
                - elapsed_start
                - (elapsed_end**2 - elapsed_start**2) / (2.0 * duration)
            )
        return (
            self.rated_power_kw + excess * integral / dt_s
        ) * self._power_limit_fraction

    def __repr__(self) -> str:
        return (
            f"Appliance(id={self.appliance_id!r}, type={self.appliance_type!r}, "
            f"priority={self.priority!r}, state={self.state!r}, "
            f"power={self.current_power_kw:.3f} kW)"
        )
