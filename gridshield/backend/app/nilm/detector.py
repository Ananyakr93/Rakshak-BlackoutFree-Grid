"""Lightweight, explainable NILM event detection for aggregate active power."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

import numpy as np

from app.twin.building_twin import BuildingTwin


@dataclass(frozen=True)
class AggregatePowerSample:
    simulation_time_s: float
    power_kw: float

    def __post_init__(self) -> None:
        if (
            not np.isfinite(self.simulation_time_s)
            or not np.isfinite(self.power_kw)
            or self.simulation_time_s < 0
            or self.power_kw < 0
        ):
            raise ValueError("simulation time and aggregate power must be non-negative")


class AggregatePowerSource(Protocol):
    """Interface implemented by synthetic or future real aggregate meters."""

    def samples(self) -> Iterable[AggregatePowerSample]: ...


@dataclass(frozen=True)
class NILMEventEstimate:
    simulation_time_s: float
    delta_power_kw: float
    previous_power_kw: float
    current_power_kw: float
    event_type: Literal["switch_on", "switch_off"]
    appliance_type: str | None
    confidence: float
    classification: Literal["classified", "ambiguous", "unknown"]
    features: dict[str, float]


class NILMEventDetector:
    """Detect power steps and classify their magnitude against known signatures."""

    DEFAULT_SIGNATURES_KW: ClassVar[dict[str, float]] = {
        "split_ac_1ton": 1.0,
        "split_ac_1_5ton": 1.5,
        "geyser_15l": 2.0,
        "ev_charger_2wheeler": 0.75,
        "ev_charger_car": 3.3,
        "ceiling_fan": 0.075,
        "water_pump": 0.75,
        "refrigerator": 0.15,
        "lighting_led": 0.04,
    }

    def __init__(
        self,
        signatures_kw: dict[str, float] | None = None,
        event_threshold_kw: float = 0.025,
        minimum_confidence: float = 0.5,
        ambiguity_margin: float = 0.08,
    ) -> None:
        if event_threshold_kw <= 0 or not 0 <= minimum_confidence <= 1:
            raise ValueError("event threshold must be positive and confidence in [0, 1]")
        if ambiguity_margin < 0:
            raise ValueError("ambiguity margin must be non-negative")
        self.signatures_kw = dict(signatures_kw or self.DEFAULT_SIGNATURES_KW)
        if any(value <= 0 for value in self.signatures_kw.values()):
            raise ValueError("appliance signatures must be positive")
        self.event_threshold_kw = event_threshold_kw
        self.minimum_confidence = minimum_confidence
        self.ambiguity_margin = ambiguity_margin

    def detect(self, samples: Iterable[AggregatePowerSample]) -> list[NILMEventEstimate]:
        events: list[NILMEventEstimate] = []
        previous: AggregatePowerSample | None = None
        for sample in samples:
            if previous is not None:
                dt = sample.simulation_time_s - previous.simulation_time_s
                if dt <= 0:
                    raise ValueError("aggregate samples must have increasing simulation times")
                delta = sample.power_kw - previous.power_kw
                if abs(delta) >= self.event_threshold_kw:
                    features = {
                        "absolute_delta_kw": abs(delta),
                        "signed_delta_kw": delta,
                        "sample_interval_s": dt,
                        "change_rate_kw_per_s": delta / dt,
                    }
                    appliance_type, confidence, classification = self._classify(abs(delta))
                    events.append(
                        NILMEventEstimate(
                            simulation_time_s=sample.simulation_time_s,
                            delta_power_kw=delta,
                            previous_power_kw=previous.power_kw,
                            current_power_kw=sample.power_kw,
                            event_type="switch_on" if delta > 0 else "switch_off",
                            appliance_type=appliance_type,
                            confidence=confidence,
                            classification=classification,
                            features=features,
                        )
                    )
            previous = sample
        return events

    def _classify(
        self, magnitude_kw: float
    ) -> tuple[str | None, float, Literal["classified", "ambiguous", "unknown"]]:
        ranked = sorted(
            (
                abs(magnitude_kw - signature) / max(signature, 0.05),
                name,
            )
            for name, signature in self.signatures_kw.items()
        )
        if not ranked:
            return None, 0.0, "unknown"
        distance, best_type = ranked[0]
        confidence = max(0.0, 1.0 - distance)
        if confidence < self.minimum_confidence:
            return None, confidence, "unknown"
        if len(ranked) > 1:
            second_confidence = max(0.0, 1.0 - ranked[1][0])
            if confidence - second_confidence <= self.ambiguity_margin:
                return None, confidence, "ambiguous"
        return best_type, confidence, "classified"


@dataclass(frozen=True)
class EstimatedApplianceState:
    building_id: str
    appliance_id: str
    appliance_type: str
    estimated_state: Literal["ON", "OFF"]
    confidence: float
    simulation_time_s: float
    source: Literal["nilm_estimate"] = "nilm_estimate"


class NILMStateEstimator:
    """Map classified events to separate estimated states; never mutates the twin."""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    def apply(
        self,
        events: Iterable[NILMEventEstimate],
        building: BuildingTwin,
    ) -> list[EstimatedApplianceState]:
        estimates: list[EstimatedApplianceState] = []
        for event in events:
            if event.classification != "classified" or event.appliance_type is None:
                continue
            match = next(
                (
                    appliance
                    for appliance in building.appliances
                    if appliance.appliance_type == event.appliance_type
                ),
                None,
            )
            if match is None:
                continue
            state: Literal["ON", "OFF"] = "ON" if event.event_type == "switch_on" else "OFF"
            self._states[match.appliance_id] = state
            estimates.append(
                EstimatedApplianceState(
                    building_id=building.building_id,
                    appliance_id=match.appliance_id,
                    appliance_type=match.appliance_type,
                    estimated_state=state,
                    confidence=event.confidence,
                    simulation_time_s=event.simulation_time_s,
                )
            )
        return estimates


def make_synthetic_signal(
    event_steps: list[tuple[int, float]],
    sample_count: int,
    sample_interval_s: float = 1.0,
    baseline_kw: float = 0.0,
    noise_std_kw: float = 0.0,
    seed: int = 42,
) -> list[AggregatePowerSample]:
    """Create reproducible aggregate meter samples for tests and experiments."""
    if sample_count < 1 or sample_interval_s <= 0 or noise_std_kw < 0:
        raise ValueError("sample count and interval must be positive; noise cannot be negative")
    rng = np.random.default_rng(seed)
    changes: dict[int, float] = {}
    for step, delta in event_steps:
        if step < 0 or step >= sample_count:
            raise ValueError("event step must be inside the generated signal")
        changes[step] = changes.get(step, 0.0) + delta
    samples: list[AggregatePowerSample] = []
    power = baseline_kw
    for index in range(sample_count):
        power += changes.get(index, 0.0)
        measured = max(0.0, power + float(rng.normal(0.0, noise_std_kw)))
        samples.append(AggregatePowerSample(index * sample_interval_s, measured))
    return samples
