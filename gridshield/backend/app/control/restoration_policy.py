"""
Staggered restoration policy for GridShield (framework.md §6.4).

Eligible when frequency >= 49.95 Hz continuously for T_stable seconds.
Release order: critical, essential, then deferrable; longest-waiting first
within each priority tier. At most one appliance is restored per agent tick.
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


_PRIORITY_ORDER = {"critical": 0, "essential": 1, "deferrable": 2}
_HEADROOM_RETRY_PU = 0.01
_FREQUENCY_RETRY_HZ = 0.005


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
        up_reserve_pu: float = 0.20,
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
        self.up_reserve_pu = up_reserve_pu
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
        # Unsafe candidates are reconsidered only after a material condition change.
        self._deferred_conditions: dict[
            tuple[str, str], tuple[frozenset[str], float, float]
        ] = {}

    def _generation_headroom_pu(self, grid_state: GridState) -> float:
        available_generation_pu = (
            1.0 + self.up_reserve_pu + grid_state.generation_disturbance_pu
        )
        return max(0.0, available_generation_pu - grid_state.demand_pu)

    def _should_retry_deferred(
        self,
        key: tuple[str, str],
        headroom_pu: float,
        frequency_hz: float,
        pickup_pu: float,
        projected_frequency_hz: float,
    ) -> bool:
        deferred = self._deferred_conditions.get(key)
        if deferred is None:
            return True
        reasons, previous_headroom_pu, previous_frequency_hz = deferred
        return (
            "capacity" in reasons
            and (
                pickup_pu <= headroom_pu + 1e-12
                or headroom_pu >= previous_headroom_pu + _HEADROOM_RETRY_PU
            )
        ) or (
            "frequency" in reasons
            and (
                projected_frequency_hz >= self.f_safe_hz
                or frequency_hz >= previous_frequency_hz + _FREQUENCY_RETRY_HZ
            )
        )

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

        # Stable enough — collect eligible candidates. A failed large pickup must
        # not prevent a smaller, safe load from being restored.
        candidates: list[tuple[int, float, BuildingTwin, Appliance]] = []
        for b in buildings:
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
                    candidates.append(
                        (_PRIORITY_ORDER[a.priority], wait_since, b, a)
                    )

        candidates.sort(
            key=lambda item: (
                item[0],
                -item[1],
                item[2].building_id,
                item[3].appliance_id,
            )
        )
        headroom_pu = self._generation_headroom_pu(grid_state)
        waiting_keys = {
            (building.building_id, appliance.appliance_id)
            for building in buildings
            for appliance in building.appliances
            if appliance.state == ApplianceState.WAITING_RESTORATION
        }
        self._deferred_conditions = {
            key: conditions
            for key, conditions in self._deferred_conditions.items()
            if key in waiting_keys
        }

        for _priority, _wait_since, b, a in candidates:
            key = (b.building_id, a.appliance_id)
            pickup_kw = _restoration_pickup_kw(a, b)
            pickup_pu = pickup_kw / max(self.area_base_kw, 1.0)
            f_projected = _projected_frequency(
                f, pickup_kw, self.area_base_kw, self.H
            )
            if not self._should_retry_deferred(
                key, headroom_pu, f, pickup_pu, f_projected
            ):
                continue

            blocked_reasons: set[str] = set()
            if pickup_pu > headroom_pu + 1e-12:
                blocked_reasons.add("capacity")
            if f_projected < self.f_safe_hz:
                blocked_reasons.add("frequency")
            if blocked_reasons:
                self._deferred_conditions[key] = (
                    frozenset(blocked_reasons),
                    headroom_pu,
                    f,
                )
                continue

            delta = a.restore(sim_time_s)
            if delta > 0:
                b.apply_demand_delta()
                self._waiting_since.pop(key, None)
                self._deferred_conditions.pop(key, None)
                restoration_mode = (
                    "Synchronized progressive"
                    if not self.stagger_enabled
                    else "Staggered"
                )
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
                break

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
        headroom_pu = self._generation_headroom_pu(grid_state)
        headroom_kw = headroom_pu * max(self.area_base_kw, 1.0)
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
                pickup_kw = _restoration_pickup_kw(appliance, building)
                projected_frequency = _projected_frequency(
                    grid_state.frequency_hz, pickup_kw, self.area_base_kw, self.H
                )
                key = (building.building_id, appliance.appliance_id)
                capacity_supported = (
                    pickup_kw / max(self.area_base_kw, 1.0) <= headroom_pu + 1e-12
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
                        "estimated_pickup_kw": pickup_kw,
                        "projected_frequency_hz": projected_frequency,
                        "capacity_supported": capacity_supported,
                        "ready": (
                            not self._frozen
                            and self._stable_timer >= self.t_stable_s
                            and grid_state.time_s >= eligible_at
                            and appliance.lockout_remaining_s(grid_state.time_s) <= 0
                            and capacity_supported
                            and projected_frequency >= self.f_safe_hz
                            and self._should_retry_deferred(
                                key,
                                headroom_pu,
                                grid_state.frequency_hz,
                                pickup_kw / max(self.area_base_kw, 1.0),
                                projected_frequency,
                            )
                        ),
                    }
                )
        queue.sort(
            key=lambda item: (
                _PRIORITY_ORDER[str(item["priority"])],
                float(item["eligible_at_s"]),
                str(item["building_id"]),
                str(item["appliance_id"]),
            )
        )
        available_generation_pu = max(
            0.0,
            1.0 + self.up_reserve_pu + grid_state.generation_disturbance_pu,
        )
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
            "available_generation_pu": available_generation_pu,
            "headroom_kw": headroom_kw,
            "completed": not queue,
            "queue": queue,
        }
