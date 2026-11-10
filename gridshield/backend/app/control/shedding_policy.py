"""
Shedding policy implementations for GridShield.

P0 — UnmanagedPolicy:    no shedding; audit-trail events only.
P1 — ADMSFeederPolicy:   emulates Southern Region ADMS feeder tripping.
P2 — PriorityEdgePolicy: appliance-level, priority-aware staged shedding (§6.3).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections import defaultdict

from app.control.restoration_policy import StaggeredRestorationPolicy
from app.schemas.events import ControlEvent
from app.schemas.scenario import GridParams
from app.twin.appliance import ApplianceState
from app.twin.building_twin import BuildingTwin
from app.twin.grid_model import GridState


class BasePolicy(ABC):
    """Abstract base for all shedding policies."""

    policy_name: str = "base"

    @abstractmethod
    def evaluate(
        self,
        grid_state: GridState,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> tuple[float, list[ControlEvent]]:
        """
        Evaluate policy for one building at one agent tick.

        Returns
        -------
        (demand_delta_kw, list[ControlEvent])
          demand_delta_kw: total kW change from this tick (-ve = load shed)
          events: every decision record (including no-ops at low frequency)
        """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_run_id() -> uuid.UUID:
    """Placeholder run_id for events created before a run ID is assigned."""
    return uuid.UUID(int=0)


def _make_event(
    run_id: uuid.UUID,
    sim_time_s: float,
    event_type: str,
    building_id: str,
    frequency_hz: float,
    reason: str,
    appliance_id: str | None = None,
    priority: str | None = None,
    power_delta_kw: float | None = None,
) -> ControlEvent:
    return ControlEvent(
        run_id=run_id,
        simulation_time_s=sim_time_s,
        event_type=event_type,
        building_id=building_id,
        appliance_id=appliance_id,
        reason=reason,
        frequency_hz=frequency_hz,
        priority=priority,
        power_delta_kw=power_delta_kw,
    )


# ---------------------------------------------------------------------------
# P0 — Unmanaged
# ---------------------------------------------------------------------------


class UnmanagedPolicy(BasePolicy):
    """
    No demand-side action. Returns empty list always.
    Logs a no-op audit event when frequency drops below S1 trigger.
    """

    policy_name = "P0_unmanaged"

    def __init__(self, run_id: uuid.UUID | None = None) -> None:
        self._run_id = run_id or _new_run_id()
        self._low_frequency_logged = False

    def evaluate(
        self,
        grid_state: GridState,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> tuple[float, list[ControlEvent]]:
        events: list[ControlEvent] = []
        if grid_state.frequency_hz < 49.85:
            if not self._low_frequency_logged:
                self._low_frequency_logged = True
                events.append(
                    _make_event(
                        self._run_id,
                        sim_time_s,
                        "no_op",
                        building.building_id,
                        grid_state.frequency_hz,
                        reason=f"P0: unmanaged — no action at f={grid_state.frequency_hz:.4f} Hz",
                    )
                )
        else:
            self._low_frequency_logged = False
        return 0.0, events


# ---------------------------------------------------------------------------
# P1 — ADMS Feeder (Southern Region emulator)
# ---------------------------------------------------------------------------


class ADMSFeederPolicy(BasePolicy):
    """
    Emulates Southern Region ADMS feeder-tripping behaviour.

    Groups of buildings are configured as feeder groups. When a stage
    threshold is sustained, the entire feeder group is tripped —
    including Essential and Critical loads (no priority awareness).

    Thresholds and hold times come from the scenario's GridParams.
    """

    policy_name = "P1_adms_feeder"

    def __init__(
        self,
        feeder_groups: dict[str, list[str]] | None = None,
        run_id: uuid.UUID | None = None,
        grid_params: GridParams | None = None,
        sample_interval_s: float = 0.5,
    ) -> None:
        """
        feeder_groups: {"stage1": [building_ids], "stage2": [...], "stage3": [...]}
        If not provided, all buildings go in stage1.
        """
        self._run_id = run_id or _new_run_id()
        self._feeder_groups: dict[str, list[str]] = feeder_groups or {}
        self.grid_params = grid_params or GridParams()
        if sample_interval_s <= 0:
            raise ValueError("sample_interval_s must be positive")
        self.sample_interval_s = sample_interval_s

        # Hold timers: how long continuously below each threshold
        self._hold: dict[str, float] = {"stage1": 0.0, "stage2": 0.0, "stage3": 0.0}
        self._last_stage_update_s: float | None = None
        self._tripped: set[str] = set()  # building_ids that have been tripped
        self._recovery_timer: float = 0.0
        self._last_recovery_update_s: float | None = None
        self._restoration_done: set[str] = set()

    def _get_stage(self, building_id: str) -> str:
        for stage, ids in self._feeder_groups.items():
            if building_id in ids:
                return stage
        return "stage1"  # default

    def evaluate(
        self,
        grid_state: GridState,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> tuple[float, list[ControlEvent]]:
        f = grid_state.frequency_hz
        dt = (
            self.sample_interval_s
            if self._last_stage_update_s is None
            else max(0.0, sim_time_s - self._last_stage_update_s)
        )
        events: list[ControlEvent] = []
        demand_delta = 0.0

        # All buildings are evaluated at the same sample time; advance each
        # feeder-wide hold timer only once per sample rather than per building.
        if dt > 0.0:
            p = self.grid_params
            for name, threshold in (
                ("stage1", p.f_s1_hz),
                ("stage2", p.f_s2_hz),
                ("stage3", p.f_s3_hz),
            ):
                if f <= threshold:
                    self._hold[name] += dt
                else:
                    self._hold[name] = 0.0
            self._last_stage_update_s = sim_time_s

        recovery_dt = (
            self.sample_interval_s
            if self._last_recovery_update_s is None
            else max(0.0, sim_time_s - self._last_recovery_update_s)
        )
        if recovery_dt > 0.0:
            self._last_recovery_update_s = sim_time_s
            if self._tripped:
                if f >= self.grid_params.f_recovery_hz:
                    self._recovery_timer += recovery_dt
                else:
                    self._recovery_timer = 0.0

        # Determine if this building's feeder should be tripped
        bid = building.building_id
        stage = self._get_stage(bid)
        p = self.grid_params
        should_trip = (
            (
                stage == "stage1"
                and f <= p.f_s1_hz
                and self._hold["stage1"] >= p.t_s1_hold_s
            )
            or (
                stage == "stage2"
                and f <= p.f_s2_hz
                and self._hold["stage2"] >= p.t_s2_hold_s
            )
            or (
                stage == "stage3"
                and f <= p.f_s3_hz
                and self._hold["stage3"] >= p.t_s3_hold_s
            )
        )

        if should_trip and bid not in self._tripped:
            # Trip entire feeder — shed ALL appliances including Critical
            self._tripped.add(bid)
            self._restoration_done.discard(bid)
            self._recovery_timer = 0.0
            self._last_recovery_update_s = sim_time_s
            for appl in building.appliances:
                if appl.state in (ApplianceState.ON, ApplianceState.RUNNING):
                    # P1 intentionally emulates an indiscriminate physical feeder trip.
                    delta = appl.force_shed(sim_time_s)
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "feeder_trip",
                            bid,
                            f,
                            reason=f"P1 ADMS feeder trip {stage} at f={f:.4f} Hz",
                            appliance_id=appl.appliance_id,
                            priority=appl.priority,
                            power_delta_kw=abs(delta) * building.weight_k,
                        )
                    )
            building.apply_demand_delta()

        # Restoration after the configured stable-frequency hold.
        if bid in self._tripped and bid not in self._restoration_done:
            if self._recovery_timer >= self.grid_params.t_p1_recovery_s:
                for appl in building.appliances:
                    appl.tick(sim_time_s)
                    if appl.state == ApplianceState.SHED:
                        appl.mark_waiting_restoration(sim_time_s)
                    if appl.state == ApplianceState.WAITING_RESTORATION:
                        delta = appl.restore(sim_time_s)
                        if delta <= 0.0:
                            continue
                        demand_delta += delta
                        events.append(
                            _make_event(
                                self._run_id,
                                sim_time_s,
                                "restore",
                                bid,
                                f,
                                reason=(
                                    "P1 ADMS restoration after "
                                    f"{self.grid_params.t_p1_recovery_s:.1f}s stable"
                                ),
                                appliance_id=appl.appliance_id,
                                priority=appl.priority,
                            )
                        )
                building.apply_demand_delta()
                restored = all(
                    appl.state in (ApplianceState.ON, ApplianceState.RUNNING)
                    for appl in building.appliances
                )
                if restored:
                    self._restoration_done.add(bid)
                    self._tripped.discard(bid)

        return demand_delta, events


# ---------------------------------------------------------------------------
# Stage hold timer helper
# ---------------------------------------------------------------------------


class StageHoldTimer:
    """
    Tracks how long frequency has been continuously at or below a threshold.
    Resets to zero if frequency rises above the threshold.
    """

    def __init__(self, threshold_hz: float, required_hold_s: float) -> None:
        self.threshold_hz = threshold_hz
        self.required_hold_s = required_hold_s
        self._accumulated_s: float = 0.0

    def update(self, frequency_hz: float, dt_s: float) -> bool:
        """
        Update the timer. Returns True if the hold condition is now met.
        dt_s is the time since last update.
        """
        below_threshold = frequency_hz <= self.threshold_hz
        if below_threshold:
            self._accumulated_s += dt_s
        else:
            self._accumulated_s = 0.0
        return below_threshold and self._accumulated_s >= self.required_hold_s

    def reset(self) -> None:
        self._accumulated_s = 0.0

    @property
    def elapsed_s(self) -> float:
        return self._accumulated_s


# ---------------------------------------------------------------------------
# P2 — Priority-aware edge policy
# ---------------------------------------------------------------------------


class PriorityEdgePolicy(BasePolicy):
    """
    Appliance-level, priority-aware staged shedding (framework.md §6.3).

    Scenario GridParams define the staged thresholds and hold times.
    Critical loads are never deliberately shed by this policy.
    Stage hold timers reset on any recovery above the stage trigger.
    """

    policy_name = "P2_priority_edge"

    def __init__(
        self,
        run_id: uuid.UUID | None = None,
        restoration_policy: StaggeredRestorationPolicy | None = None,
        policy_name: str | None = None,
        enable_restoration: bool = True,
        grid_params: GridParams | None = None,
        sample_interval_s: float = 0.5,
    ) -> None:
        self._run_id = run_id or _new_run_id()
        if policy_name is not None:
            self.policy_name = policy_name
        self.restoration_policy = (
            restoration_policy or StaggeredRestorationPolicy(run_id=self._run_id)
            if enable_restoration
            else None
        )
        self.restoration_enabled = enable_restoration
        self.grid_params = grid_params or GridParams()
        if sample_interval_s <= 0:
            raise ValueError("sample_interval_s must be positive")
        self.sample_interval_s = sample_interval_s
        # Per-building stage timers — keyed by building_id
        self._timers: dict[str, dict[str, StageHoldTimer]] = defaultdict(
            lambda: {
                "s0": StageHoldTimer(
                    self.grid_params.f_s0_hz,
                    self.grid_params.t_s0_hold_s,
                ),
                "s1": StageHoldTimer(
                    self.grid_params.f_s1_hz,
                    self.grid_params.t_s1_hold_s,
                ),
                "o1": StageHoldTimer(
                    self.grid_params.f_o1_hz,
                    self.grid_params.t_o1_hold_s,
                ),  # checks from above
            }
        )
        self._s2_active: dict[str, bool] = defaultdict(bool)
        self._s3_active: dict[str, bool] = defaultdict(bool)

    def evaluate(
        self,
        grid_state: GridState,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> tuple[float, list[ControlEvent]]:
        f = grid_state.frequency_hz
        rocof = grid_state.rocof_hz_per_s
        dt = self.sample_interval_s

        bid = building.building_id
        timers = self._timers[bid]
        events: list[ControlEvent] = []
        demand_delta = 0.0

        # Update timers (O1 uses >= threshold, so invert for the helper)
        s0_triggered = timers["s0"].update(f, dt)
        s1_triggered = timers["s1"].update(f, dt)
        # S2: instantaneous (or RoCoF-based)
        s2_triggered = (
            f <= self.grid_params.f_s2_hz
            or rocof <= self.grid_params.rocof_s2_threshold
        )
        # S3: instantaneous
        s3_triggered = f <= self.grid_params.f_s3_hz
        # O1: frequency above its configured threshold sustained.
        o1_triggered = f >= self.grid_params.f_o1_hz
        if o1_triggered:
            timers["o1"]._accumulated_s += dt
        else:
            timers["o1"].reset()
        o1_ready = timers["o1"].elapsed_s >= self.grid_params.t_o1_hold_s

        if not s0_triggered:
            for appliance in building.appliances:
                if appliance.priority == "deferrable":
                    appliance.set_power_limit_fraction(1.0, sim_time_s)
            demand_delta += building.apply_demand_delta()

        # ------------------------------------------------------------------
        # Shedding actions (most severe takes priority)
        # ------------------------------------------------------------------

        # S3: shed remaining Essential (never Critical)
        if s3_triggered and not self._s3_active[bid]:
            self._s3_active[bid] = True
            for appl in building.get_shed_candidates_at(sim_time_s, priority="essential"):
                delta = appl.shed(sim_time_s)
                if delta != 0.0:
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "shed_essential",
                            bid,
                            f,
                            reason=(
                                f"P2 S3: f={f:.4f} Hz ≤ "
                                f"{self.grid_params.f_s3_hz:.2f}; shed essential"
                            ),
                            appliance_id=appl.appliance_id,
                            priority="essential",
                            power_delta_kw=abs(delta) * building.weight_k,
                        )
                    )
            building.apply_demand_delta()

        elif s2_triggered:
            # S2: shed Deferrable then Essential
            for appl in building.get_shed_candidates_at(sim_time_s, priority="deferrable"):
                delta = appl.shed(sim_time_s)
                if delta != 0.0:
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "shed_deferrable",
                            bid,
                            f,
                            reason=(
                                f"P2 S2: f={f:.4f} Hz ≤ "
                                f"{self.grid_params.f_s2_hz:.2f} or "
                                f"RoCoF={rocof:.3f} Hz/s ≤ "
                                f"{self.grid_params.rocof_s2_threshold:.3f}; "
                                "shed deferrable"
                            ),
                            appliance_id=appl.appliance_id,
                            priority="deferrable",
                            power_delta_kw=abs(delta) * building.weight_k,
                        )
                    )
            for appl in building.get_shed_candidates_at(sim_time_s, priority="essential"):
                delta = appl.shed(sim_time_s)
                if delta != 0.0:
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "shed_essential",
                            bid,
                            f,
                            reason=(
                                f"P2 S2: f={f:.4f} Hz ≤ "
                                f"{self.grid_params.f_s2_hz:.2f}; shed essential"
                            ),
                            appliance_id=appl.appliance_id,
                            priority="essential",
                            power_delta_kw=abs(delta) * building.weight_k,
                        )
                    )
            building.apply_demand_delta()

        elif s1_triggered:
            # S1: shed Deferrable only
            for appl in building.get_shed_candidates_at(sim_time_s, priority="deferrable"):
                delta = appl.shed(sim_time_s)
                if delta != 0.0:
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "shed_deferrable",
                            bid,
                            f,
                            reason=(
                                f"P2 S1: f={f:.4f} Hz ≤ "
                                f"{self.grid_params.f_s1_hz:.2f} for ≥"
                                f"{self.grid_params.t_s1_hold_s:.1f}s; shed deferrable"
                            ),
                            appliance_id=appl.appliance_id,
                            priority="deferrable",
                            power_delta_kw=abs(delta) * building.weight_k,
                        )
                    )
            building.apply_demand_delta()

        elif s0_triggered:
            # S0 Advisory: throttle Deferrable to 70% rated (soft action)
            for appl in building.appliances:
                if (
                    appl.priority == "deferrable"
                    and appl.enrolled
                    and appl.state == ApplianceState.ON
                ):
                    appl.set_power_limit_fraction(0.7, sim_time_s)
            delta = building.apply_demand_delta()
            if delta != 0.0:
                demand_delta += delta
                events.append(
                    _make_event(
                        self._run_id,
                        sim_time_s,
                        "throttle_deferrable",
                        bid,
                        f,
                        reason=(
                            f"P2 S0: f={f:.4f} Hz ≤ {self.grid_params.f_s0_hz:.2f} "
                            f"for ≥{self.grid_params.t_s0_hold_s:.1f}s; "
                            "throttle deferrable to 70%"
                        ),
                        power_delta_kw=abs(delta) * building.weight_k,
                    )
                )

        # Reset S3 active flag when frequency recovers above S3 threshold
        if f > self.grid_params.f_s3_hz:
            self._s3_active[bid] = False

        # ------------------------------------------------------------------
        # O1 Absorb: start enrolled OFF Deferrable loads
        # ------------------------------------------------------------------
        if o1_ready and f >= self.grid_params.f_o1_hz:
            for appl in building.appliances:
                if (
                    appl.priority == "deferrable"
                    and appl.enrolled
                    and appl.state == ApplianceState.OFF
                ):
                    delta = appl.start_from_off(sim_time_s)
                    if delta == 0.0:
                        continue
                    demand_delta += delta
                    events.append(
                        _make_event(
                            self._run_id,
                            sim_time_s,
                            "absorb_deferrable",
                            bid,
                            f,
                            reason=(
                                f"P2 O1: f={f:.4f} Hz ≥ "
                                f"{self.grid_params.f_o1_hz:.2f} for ≥"
                                f"{self.grid_params.t_o1_hold_s:.1f}s; absorb deferrable"
                            ),
                            appliance_id=appl.appliance_id,
                            priority="deferrable",
                        )
                    )
            building.apply_demand_delta()

        return demand_delta, events
