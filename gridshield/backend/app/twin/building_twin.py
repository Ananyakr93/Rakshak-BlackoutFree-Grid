"""
Building digital twin for GridShield.

Each BuildingTwin holds a collection of Appliance objects and tracks
aggregate demand. The weight_k field scales this building to represent
k real buildings in Mode A (scaled area) simulations.
"""

from __future__ import annotations

from app.schemas.scenario import BuildingConfig
from app.twin.appliance import Appliance, ApplianceState


class BuildingTwin:
    """
    Virtual building with appliances and aggregate demand tracking.

    apply_demand_delta() recomputes total_demand_kw from appliance states,
    so the total is always exact (no floating-point drift from incremental
    accumulation).
    """

    def __init__(
        self,
        building_id: str,
        weight_k: int = 1,
        appliances: list[Appliance] | None = None,
    ) -> None:
        self.building_id = building_id
        self.weight_k = weight_k
        self.appliances: list[Appliance] = appliances or []

        # Compute initial total from appliance states
        self.total_demand_kw: float = sum(a.current_power_kw for a in self.appliances)
        self._prev_demand_kw: float = self.total_demand_kw

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: BuildingConfig, initial_sim_time_s: float = 0.0) -> BuildingTwin:
        """Construct a BuildingTwin from a BuildingConfig schema."""
        appliances = [
            Appliance(
                appliance_id=ac.appliance_id,
                building_id=config.building_id,
                appliance_type=ac.appliance_type,
                priority=ac.priority,
                rated_power_kw=ac.rated_power_kw,
                min_on_time_s=ac.min_on_time_s,
                min_off_time_s=ac.min_off_time_s,
                max_shed_minutes=ac.max_shed_minutes,
                enrolled=ac.enrolled,
                initial_state=ApplianceState(ac.initial_state),
                initial_sim_time_s=initial_sim_time_s,
                compressor_lockout_s=ac.compressor_lockout_s,
                inrush_multiplier=ac.inrush_multiplier,
                inrush_duration_s=ac.inrush_duration_s,
                startup_recovery_profile=ac.startup_recovery_profile,
            )
            for ac in config.appliances
        ]
        return cls(
            building_id=config.building_id,
            weight_k=config.weight_k,
            appliances=appliances,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_shed_candidates(self, priority: str | None = None) -> list[Appliance]:
        """
        Return enrolled, ON appliances eligible to shed.
        Optionally filtered to a specific priority tier.
        """
        candidates = [
            a
            for a in self.appliances
            if a.can_shed(0.0)  # sim_time checked by caller via can_shed
        ]
        if priority is not None:
            candidates = [a for a in candidates if a.priority == priority]
        return candidates

    def get_shed_candidates_at(
        self, sim_time_s: float, priority: str | None = None
    ) -> list[Appliance]:
        """Return shed candidates with correct time-based lockout checks."""
        candidates = [a for a in self.appliances if a.can_shed(sim_time_s)]
        if priority is not None:
            candidates = [a for a in candidates if a.priority == priority]
        return candidates

    def get_restoration_candidates(self) -> list[Appliance]:
        """Return appliances in WAITING_RESTORATION state."""
        return [a for a in self.appliances if a.state == ApplianceState.WAITING_RESTORATION]

    def get_restoration_candidates_at(self, sim_time_s: float) -> list[Appliance]:
        """Return WAITING_RESTORATION appliances that also satisfy min_off_time_s."""
        return [a for a in self.appliances if a.can_restore(sim_time_s)]

    def apply_demand_delta(self) -> float:
        """
        Recompute total_demand_kw from appliance states.
        Returns the change in kW vs the previous call.
        """
        self._prev_demand_kw = self.total_demand_kw
        self.total_demand_kw = sum(a.current_power_kw for a in self.appliances)
        return self.total_demand_kw - self._prev_demand_kw

    def tick(self, sim_time_s: float, dt_s: float = 0.0) -> None:
        """Advance all appliance timer logic."""
        for a in self.appliances:
            a.tick(sim_time_s, dt_s)

    def __repr__(self) -> str:
        return (
            f"BuildingTwin(id={self.building_id!r}, "
            f"appliances={len(self.appliances)}, "
            f"demand={self.total_demand_kw:.3f} kW)"
        )
