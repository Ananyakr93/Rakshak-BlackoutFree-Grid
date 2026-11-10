"""Transparent branch-current estimates for the reduced-order city twin."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.twin.building_twin import BuildingTwin

NOMINAL_LINE_VOLTAGE_V = 400.0
ASSUMED_POWER_FACTOR = 0.95


@dataclass(frozen=True)
class FeederBranchEstimate:
    building_id: str
    active_power_kw: float
    estimated_current_a: float


def estimate_feeder_branches(
    buildings: Iterable[BuildingTwin],
) -> list[FeederBranchEstimate]:
    """Estimate balanced three-phase branch current from each twin's served load.

    The model assumes a nominal 400 V line-to-line supply and 0.95 power
    factor. It does not solve voltage drops, reactive power, protection, or
    feeder impedances; these values are model estimates, not meter readings.
    """
    estimates: list[FeederBranchEstimate] = []
    for building in buildings:
        power_kw = sum(
            appliance.current_power_kw * building.weight_k
            for appliance in building.appliances
        )
        current_a = (
            power_kw * 1000.0
            / (math.sqrt(3.0) * NOMINAL_LINE_VOLTAGE_V * ASSUMED_POWER_FACTOR)
        )
        estimates.append(
            FeederBranchEstimate(
                building_id=building.building_id,
                active_power_kw=power_kw,
                estimated_current_a=current_a,
            )
        )
    return estimates
