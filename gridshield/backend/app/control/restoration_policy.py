"""
Staggered restoration policy for GridShield (framework.md §6.4).

Eligible when frequency >= 49.95 Hz continuously for T_stable seconds.
Release order: by waiting time (longest-waiting first).
Deterministic stagger: delay = base + (hash(building_id, incident_id, seed) % window).
Projection check: estimated post-pickup frequency must stay >= 49.90 Hz.
Any relapse below S1 trigger (49.85 Hz) freezes all pending restoration.
"""

from __future__ import annotations

import hashlib
import uuid

from app.schemas.events import ControlEvent
from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin
from app.twin.grid_model import GridState


def _stagger_delay(
    building_id: str,
    incident_id: str,
    seed: int,
    base_delay_s: float = 5.0,
    window_s: int = 60,
    appliance_id: str = "",
) -> float:
    """
    Compute a deterministic stagger delay for a building.

    delay = base_delay_s + hash(building_id, appliance_id, incident_id, seed) % window_s
    """
    key = f"{building_id}|{appliance_id}|{incident_id}|{seed}"
    digest = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    return base_delay_s + (digest % window_s)


def _projected_frequency(
    f_current: float,
    appliance_power_kw: float,
    area_base_kw: float,
    H: float,
) -> float:
    """
    Estimate post-pickup frequency after restoring one appliance.

    Simplified: Δf ≈ -ΔP / (2H)  (first-order approximation in per-unit)
    """
    delta_p_pu = appliance_power_kw / max(area_base_kw, 1.0)
    return f_current - delta_p_pu / (2.0 * H)


def _restoration_pickup_kw(appliance: Appliance, building: BuildingTwin) -> float:
    startup_factor = (
        appliance.inrush_multiplier if appliance.inrush_duration_s > 0 else 1.0
    )
    return appliance.rated_power_kw * startup_factor * building.weight_k


class StaggeredRestorationPolicy:
    """
    Manages staggered, projection-checked restoration across all buildings.

    Call tick() once per agent sample interval. Returns a list of
    ControlEvents for any restoration actions performed this tick.
    """

    def __init__(
        self,
        run_id: uuid.UUID | None = None,
        t_stable_s: float = 60.0,
        f_recovery_hz: float = 49.95,
        f_freeze_hz: float = 49.85,
        f_safe_hz: float = 49.90,
        H: float = 4.0,
        area_base_kw: float = 100.0,
        base_delay_s: float = 5.0,
        window_s: int = 60,
        stagger_enabled: bool = True,
        sample_interval_s: float = 0.5,
    ) -> None:
        self._run_id = run_id or uuid.UUID(int=0)
        self.t_stable_s = t_stable_s
        self.f_recovery_hz = f_recovery_hz
        self.f_freeze_hz = f_freeze_hz
        self.f_safe_hz = f_safe_hz
        self.H = H
        self.area_base_kw = area_base_kw
        self.base_delay_s = base_delay_s
        self.window_s = window_s
        self.stagger_enabled = stagger_enabled
        if sample_interval_s <= 0:
            raise ValueError("sample_interval_s must be positive")
        self.sample_interval_s = sample_interval_s

        self._stable_timer: float = 0.0
        self._frozen: bool = False
        # scheduled_time -> (building_id, appliance_id)
        self._scheduled: dict[float, tuple] = {}
        # Track when each appliance entered WAITING_RESTORATION
        self._waiting_since: dict[tuple[str, str], float] = {}

    def tick(
        self,
        grid_state: GridState,
        buildings: list[BuildingTwin],
        incident_id: str,
        seed: int,
        sim_time_s: float,
    ) -> list[ControlEvent]:
        """
        Evaluate restoration for all buildings.

        Returns list of ControlEvents for restorations performed this tick.
        """
        f = grid_state.frequency_hz
        dt = self.sample_interval_s
        events: list[ControlEvent] = []

        # Track new WAITING_RESTORATION appliances
        for b in buildings:
            for a in b.appliances:
                waiting_key = (b.building_id, a.appliance_id)
                if (
                    a.state == ApplianceState.WAITING_RESTORATION
                    and waiting_key not in self._waiting_since
                ):
                    self._waiting_since[waiting_key] = sim_time_s
        waiting_ids = {
            (building.building_id, appliance.appliance_id)
            for building in buildings
            for appliance in building.appliances
            if appliance.state == ApplianceState.WAITING_RESTORATION
        }
        self._waiting_since = {
            waiting_key: waiting_since
            for waiting_key, waiting_since in self._waiting_since.items()
            if waiting_key in waiting_ids
        }

        # Freeze on relapse below S1 threshold
        if f < self.f_freeze_hz:
            self._frozen = True
            self._stable_timer = 0.0
            return events

        # Unfreeze only once stable timer reaches required duration AFTER a freeze
        if f >= self.f_recovery_hz:
            self._stable_timer += dt
        else:
            self._stable_timer = 0.0

        # Unfreeze: requires stable timer to complete again after any freeze
        if self._frozen:
            if self._stable_timer >= self.t_stable_s:
                self._frozen = False
            else:
                return events

        if self._stable_timer < self.t_stable_s:
            return events

        # Stable enough — collect all WAITING_RESTORATION candidates
        candidates = []
        waiting_count = 0
        for b in buildings:
            waiting_count += len(b.get_restoration_candidates())
            for a in b.get_restoration_candidates_at(sim_time_s):
                waiting_key = (b.building_id, a.appliance_id)
                wait_since = self._waiting_since.get(waiting_key, sim_time_s)
                delay = (
                    _stagger_delay(
                        b.building_id,
                        incident_id,
                        seed,
                        self.base_delay_s,
                        self.window_s,
                        appliance_id=a.appliance_id,
                    )
                    if self.stagger_enabled
                    else 0.0
                )
                eligible_at = wait_since + delay + self.t_stable_s
                if sim_time_s >= eligible_at:
                    candidates.append((wait_since, b, a))

        if not self.stagger_enabled and len(candidates) != waiting_count:
            return events

        # Sort by longest waiting first
        candidates.sort(key=lambda x: x[0], reverse=True)

        if not self.stagger_enabled:
            total_pickup_kw = sum(
                _restoration_pickup_kw(appliance, building)
                for _, building, appliance in candidates
            )
            projected_frequency = _projected_frequency(
                f, total_pickup_kw, self.area_base_kw, self.H
            )
            if projected_frequency < self.f_safe_hz:
                return events

        restored_power_kw = 0.0
        for _wait_since, b, a in candidates:
            pickup_kw = _restoration_pickup_kw(a, b)
            # Projection check
            f_projected = _projected_frequency(
                f,
                restored_power_kw + pickup_kw,
                self.area_base_kw,
                self.H,
            )
            if f_projected < self.f_safe_hz:
                break  # stop restoring this tick

            delta = a.restore(sim_time_s)
            if delta > 0:
                restored_power_kw += pickup_kw
                b.apply_demand_delta()
                self._waiting_since.pop((b.building_id, a.appliance_id), None)
                restoration_mode = "Synchronized batch" if not self.stagger_enabled else "Staggered"
                events.append(
                    ControlEvent(
                        run_id=self._run_id,
                        simulation_time_s=sim_time_s,
                        event_type="restore",
                        building_id=b.building_id,
                        appliance_id=a.appliance_id,
                        reason=(
                            f"{restoration_mode} restore: f={f:.4f} Hz stable ≥{self.t_stable_s}s; "
                            f"projected f={f_projected:.4f} Hz ≥ {self.f_safe_hz} Hz"
                        ),
                        frequency_hz=f,
                        priority=a.priority,
                    )
                )

        return events

    def snapshot(
        self,
        grid_state: GridState,
        buildings: list[BuildingTwin],
        incident_id: str,
        seed: int,
    ) -> dict[str, object]:
        """Return the active safety gate and deterministic restoration queue."""
        queue: list[dict[str, object]] = []
        for building in buildings:
            for appliance in building.appliances:
                if (
                    appliance.state != ApplianceState.WAITING_RESTORATION
                    and not appliance.restoration_pending
                ):
                    continue
                waiting_key = (building.building_id, appliance.appliance_id)
                waiting_since = self._waiting_since.get(waiting_key, appliance.last_state_change_s)
                delay = (
                    _stagger_delay(
                        building.building_id,
                        incident_id,
                        seed,
                        self.base_delay_s,
                        self.window_s,
                        appliance_id=appliance.appliance_id,
                    )
                    if self.stagger_enabled
                    else 0.0
                )
                eligible_at = waiting_since + delay + self.t_stable_s
                projected_frequency = _projected_frequency(
                    grid_state.frequency_hz,
                    appliance.rated_power_kw * building.weight_k,
                    self.area_base_kw,
                    self.H,
                )
                queue.append(
                    {
                        "building_id": building.building_id,
                        "appliance_id": appliance.appliance_id,
                        "appliance_type": appliance.appliance_type,
                        "priority": appliance.priority,
                        "state": appliance.state.value,
                        "lockout_remaining_s": appliance.lockout_remaining_s(
                            grid_state.time_s
                        ),
                        "waiting_since_s": waiting_since,
                        "stagger_delay_s": delay,
                        "eligible_at_s": eligible_at,
                        "projected_frequency_hz": projected_frequency,
                        "ready": (
                            not self._frozen
                            and self._stable_timer >= self.t_stable_s
                            and grid_state.time_s >= eligible_at
                            and projected_frequency >= self.f_safe_hz
                        ),
                    }
                )
        queue.sort(key=lambda item: (float(item["eligible_at_s"]), str(item["building_id"])))
        return {
            "enabled": True,
            "frozen": self._frozen,
            "frequency_hz": grid_state.frequency_hz,
            "frequency_gate_hz": self.f_recovery_hz,
            "freeze_below_hz": self.f_freeze_hz,
            "projection_floor_hz": self.f_safe_hz,
            "stable_timer_s": self._stable_timer,
            "required_stability_s": self.t_stable_s,
            "stagger_enabled": self.stagger_enabled,
            "queue": queue,
        }
