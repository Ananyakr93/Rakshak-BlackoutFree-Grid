"""
Disturbance profiles for GridShield simulation scenarios.

Each profile computes the per-unit power imbalance at a given simulation
time. Positive values represent generation loss or demand surplus (frequency
falls); negative values represent demand reduction or solar surplus
(frequency rises — over-frequency scenario N3).

All profiles are pure — no side effects — and accept an optional
numpy.random.Generator for stochastic variation.

Factory
-------
  make_disturbance(config, seed) -> DisturbanceProfile
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from app.schemas.scenario import DisturbanceConfig


class DisturbanceProfile(ABC):
    """Abstract base class for all disturbance profiles."""

    @abstractmethod
    def get_disturbance_pu(self, sim_time_s: float) -> float:
        """
        Return per-unit power imbalance at sim_time_s.

        +ve → generation loss or demand surplus  (frequency falls)
        -ve → demand reduction or solar surplus  (frequency rises)
        """
        raise NotImplementedError

    def get_disturbance_components(self, sim_time_s: float) -> tuple[float, float]:
        """Return signed generation change and exogenous demand change in pu."""
        return -self.get_disturbance_pu(sim_time_s), 0.0


class GenerationLossDisturbance(DisturbanceProfile):
    """
    Step-up disturbance at start_time_s, held for duration_s,
    then linear recovery ramp back to zero over recovery_ramp_s.
    """

    def __init__(
        self,
        start_time_s: float,
        magnitude_pu: float,
        duration_s: float,
        recovery_ramp_s: float = 30.0,
    ) -> None:
        self.start = start_time_s
        self.magnitude = magnitude_pu
        self.duration = duration_s
        self.ramp = recovery_ramp_s

    def get_disturbance_pu(self, sim_time_s: float) -> float:
        t = sim_time_s
        if t < self.start:
            return 0.0
        elapsed = t - self.start
        if elapsed <= self.duration:
            return self.magnitude
        ramp_elapsed = elapsed - self.duration
        if ramp_elapsed >= self.ramp:
            return 0.0
        return self.magnitude * (1.0 - ramp_elapsed / self.ramp)


class DemandSurgeDisturbance(DisturbanceProfile):
    """
    Sudden increase in demand — same shape as GenerationLossDisturbance,
    positive sign (frequency falls).
    """

    def __init__(
        self,
        start_time_s: float,
        magnitude_pu: float,
        duration_s: float,
        recovery_ramp_s: float = 30.0,
    ) -> None:
        self._inner = GenerationLossDisturbance(
            start_time_s, magnitude_pu, duration_s, recovery_ramp_s
        )

    def get_disturbance_pu(self, sim_time_s: float) -> float:
        return self._inner.get_disturbance_pu(sim_time_s)

    def get_disturbance_components(self, sim_time_s: float) -> tuple[float, float]:
        return 0.0, self.get_disturbance_pu(sim_time_s)


class CombinedDisturbance(DisturbanceProfile):
    """
    Simultaneous generation loss and demand surge.
    Sum of both components — produces a larger overall imbalance.
    """

    def __init__(
        self,
        gen_loss: GenerationLossDisturbance,
        demand_surge: DemandSurgeDisturbance,
    ) -> None:
        self.gen_loss = gen_loss
        self.demand_surge = demand_surge

    def get_disturbance_pu(self, sim_time_s: float) -> float:
        return (
            self.gen_loss.get_disturbance_pu(sim_time_s)
            + self.demand_surge.get_disturbance_pu(sim_time_s)
        )

    def get_disturbance_components(self, sim_time_s: float) -> tuple[float, float]:
        generation_delta, _ = self.gen_loss.get_disturbance_components(sim_time_s)
        _, demand_delta = self.demand_surge.get_disturbance_components(sim_time_s)
        return generation_delta, demand_delta


class SolarSurplusDisturbance(DisturbanceProfile):
    """
    Excess solar injection causing over-frequency.
    Returns a negative disturbance value (demand < generation → f rises).
    This is the N3 scenario (framework.md §5.2).
    """

    def __init__(
        self,
        start_time_s: float,
        magnitude_pu: float,
        duration_s: float,
        recovery_ramp_s: float = 30.0,
    ) -> None:
        self._inner = GenerationLossDisturbance(
            start_time_s, magnitude_pu, duration_s, recovery_ramp_s
        )

    def get_disturbance_pu(self, sim_time_s: float) -> float:
        return -self._inner.get_disturbance_pu(sim_time_s)

    def get_disturbance_components(self, sim_time_s: float) -> tuple[float, float]:
        return -self.get_disturbance_pu(sim_time_s), 0.0


class SolarCloudDropDisturbance(DisturbanceProfile):
    """Cloud cover reduces PV output by a fraction of the configured solar share."""

    def __init__(
        self,
        start_time_s: float,
        solar_share_pu: float,
        reduction_fraction: float,
        duration_s: float,
        recovery_ramp_s: float = 30.0,
    ) -> None:
        self._profile = GenerationLossDisturbance(
            start_time_s,
            solar_share_pu * reduction_fraction,
            duration_s,
            recovery_ramp_s,
        )

    def get_disturbance_pu(self, sim_time_s: float) -> float:
        return self._profile.get_disturbance_pu(sim_time_s)

    def get_disturbance_components(self, sim_time_s: float) -> tuple[float, float]:
        return -self._profile.get_disturbance_pu(sim_time_s), 0.0


def make_disturbance(config: DisturbanceConfig, seed: int = 42) -> DisturbanceProfile:
    """
    Factory: construct the correct DisturbanceProfile from a DisturbanceConfig.

    The seed parameter is accepted for API consistency (future stochastic profiles).
    """
    _ = np.random.default_rng(seed)  # reserved for future stochastic variation

    if config.type == "generation_loss":
        return GenerationLossDisturbance(
            config.start_time_s, config.magnitude_pu,
            config.duration_s, config.recovery_ramp_s,
        )
    if config.type == "demand_surge":
        return DemandSurgeDisturbance(
            config.start_time_s, config.magnitude_pu,
            config.duration_s, config.recovery_ramp_s,
        )
    if config.type == "combined":
        half = config.magnitude_pu / 2.0
        gen = GenerationLossDisturbance(
            config.start_time_s, half, config.duration_s, config.recovery_ramp_s
        )
        dem = DemandSurgeDisturbance(
            config.start_time_s, half, config.duration_s, config.recovery_ramp_s
        )
        return CombinedDisturbance(gen, dem)
    if config.type == "solar_surplus":
        return SolarSurplusDisturbance(
            config.start_time_s, config.magnitude_pu,
            config.duration_s, config.recovery_ramp_s,
        )
    if config.type == "solar_cloud_drop":
        if config.solar_share_pu is None:
            raise ValueError("solar_cloud_drop requires solar_share_pu")
        return SolarCloudDropDisturbance(
            config.start_time_s,
            config.solar_share_pu,
            config.magnitude_pu,
            config.duration_s,
            config.recovery_ramp_s,
        )
    raise ValueError(f"Unknown disturbance type: {config.type!r}")
