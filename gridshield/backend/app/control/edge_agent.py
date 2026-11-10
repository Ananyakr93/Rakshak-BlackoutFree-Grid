"""
Virtual edge agent for GridShield.

One EdgeAgent is instantiated per BuildingTwin. On each agent tick it:
  1. Evaluates the configured shedding policy.
  2. Returns the aggregate demand delta and a list of ControlEvents.

The restoration policy is held on the policy object (P2) or invoked
separately via the simulation clock.
"""

from __future__ import annotations

from enum import Enum

from app.control.shedding_policy import BasePolicy
from app.schemas.events import ControlEvent
from app.twin.building_twin import BuildingTwin
from app.twin.grid_model import GridState


class OperatingMode(str, Enum):
    CENTRALIZED = "CENTRALIZED"
    DISTRIBUTED = "DISTRIBUTED"
    COMMUNICATION_DEGRADED = "COMMUNICATION_DEGRADED"
    ISLANDED_AUTONOMOUS = "ISLANDED_AUTONOMOUS"


class EdgeAgent:
    """
    Per-building virtual edge controller.

    Receives grid state each tick, evaluates the policy, and returns
    the demand delta and control events for that tick.
    """

    def __init__(
        self,
        building: BuildingTwin,
        policy: BasePolicy,
        operating_mode: OperatingMode = OperatingMode.DISTRIBUTED,
        communication_loss_grace_s: float = 5.0,
    ) -> None:
        self.building_id = building.building_id
        self.building = building
        self.policy = policy
        if communication_loss_grace_s < 0:
            raise ValueError("communication loss grace period must be non-negative")
        self.operating_mode = operating_mode
        self._connected_mode = operating_mode
        self._communication_loss_grace_s = communication_loss_grace_s
        self._communication_lost_at_s: float | None = None
        self.evaluation_count = 0
        self.last_decision: str | None = None
        self.last_decision_reason: str | None = None
        self.last_decision_time_s: float | None = None

    def set_communication_available(self, available: bool, sim_time_s: float) -> None:
        """Track communication mode transitions on simulation time."""
        if self._connected_mode == OperatingMode.ISLANDED_AUTONOMOUS:
            self._communication_lost_at_s = 0.0
            self.operating_mode = OperatingMode.ISLANDED_AUTONOMOUS
            return
        if available:
            self._communication_lost_at_s = None
            self.operating_mode = self._connected_mode
            return
        if self._communication_lost_at_s is None:
            self._communication_lost_at_s = sim_time_s
        if self._connected_mode == OperatingMode.COMMUNICATION_DEGRADED:
            self.operating_mode = OperatingMode.COMMUNICATION_DEGRADED
            return
        elapsed = sim_time_s - self._communication_lost_at_s
        self.operating_mode = (
            OperatingMode.ISLANDED_AUTONOMOUS
            if elapsed >= self._communication_loss_grace_s
            else OperatingMode.COMMUNICATION_DEGRADED
        )

    @property
    def should_evaluate_policy(self) -> bool:
        """Apply each configured mode's dispatch behavior during communication loss."""
        if self.communication_available:
            return True
        if self._connected_mode == OperatingMode.CENTRALIZED:
            return self.operating_mode == OperatingMode.ISLANDED_AUTONOMOUS
        return self._connected_mode != OperatingMode.COMMUNICATION_DEGRADED

    @property
    def communication_available(self) -> bool:
        return (
            self._communication_lost_at_s is None
            and self._connected_mode != OperatingMode.ISLANDED_AUTONOMOUS
        )

    def tick(
        self,
        grid_state: GridState,
        sim_time_s: float,
        incident_id: str,
        seed: int,
    ) -> tuple[float, list[ControlEvent]]:
        """
        One agent evaluation cycle.

        Returns
        -------
        (demand_delta_kw, list[ControlEvent])
          demand_delta_kw: -ve for load shed, +ve for load add/restore
        """
        demand_delta, events = self.policy.evaluate(grid_state, self.building, sim_time_s)
        self.evaluation_count += 1
        self.last_decision_time_s = sim_time_s
        if events:
            latest = events[-1]
            self.last_decision = latest.event_type
            self.last_decision_reason = latest.reason
        else:
            self.last_decision = "monitor"
            self.last_decision_reason = "No protection action was required at this sample."
        return demand_delta, events
