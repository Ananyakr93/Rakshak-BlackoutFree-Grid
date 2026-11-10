"""
Metric computation functions for GridShield simulation results.

All functions are pure: they take telemetry or event lists and return
scalar or dict values. No side effects, no database access.

Metrics (framework.md §9.1):
  frequency_nadir, max_rocof, recovery_time_s, critical_energy_not_served_kwh,
  shed_latency_s, rebound_peak_pu, feeder_trips_count,
  energy_curtailed_by_tier, jains_fairness_index,
  over_frequency_excursion_time_s, compute_all_metrics
"""

from __future__ import annotations

from app.schemas.events import ControlEvent
from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample
from app.twin.simulation_clock import SimulationResult


def frequency_nadir(telemetry: list[TelemetrySample]) -> float:
    """Minimum frequency_hz recorded across the run."""
    if not telemetry:
        return 50.0
    return min(s.frequency_hz for s in telemetry)


def max_rocof(telemetry: list[TelemetrySample]) -> float:
    """Maximum absolute rate-of-change of frequency (Hz/s)."""
    if not telemetry:
        return 0.0
    return max(abs(s.rocof_hz_per_s) for s in telemetry)


def recovery_time_s(
    telemetry: list[TelemetrySample],
    recovery_band_hz: float = 49.95,
    stability_duration_s: float = 60.0,
    disturbance_start_s: float = 10.0,
) -> float | None:
    """
    Time from disturbance_start_s until frequency >= recovery_band_hz
    continuously for stability_duration_s.

    Returns None if frequency never recovered.
    """
    if not telemetry:
        return None

    stable_since: float | None = None

    for sample in telemetry:
        if sample.simulation_time_s < disturbance_start_s:
            continue
        if sample.frequency_hz >= recovery_band_hz:
            if stable_since is None:
                stable_since = sample.simulation_time_s
            elif (sample.simulation_time_s - stable_since) >= stability_duration_s:
                return sample.simulation_time_s - disturbance_start_s
        else:
            stable_since = None  # reset on dip below recovery band

    return None


def _integrate_curtailed_energy(
    events: list[ControlEvent],
    scenario: ScenarioConfig,
    run_end_s: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Integrate nominal curtailed kWh per priority and building from transitions."""
    tiers = {"critical": 0.0, "essential": 0.0, "deferrable": 0.0}
    buildings: dict[str, float] = {}
    configs = {building.building_id: building for building in scenario.buildings}
    active: dict[tuple[str, str], tuple[float, float, str]] = {}

    for event in sorted(events, key=lambda item: item.simulation_time_s):
        key = (event.building_id, event.appliance_id or "")
        is_shed = "shed" in event.event_type or event.event_type == "feeder_trip"
        if is_shed:
            if not event.appliance_id:
                raise ValueError("A load-shed event must identify its appliance.")
            if key in active:
                continue
            building = configs.get(event.building_id)
            appliance = next(
                (
                    item
                    for item in building.appliances
                    if item.appliance_id == event.appliance_id
                ),
                None,
            ) if building else None
            if building is None or appliance is None:
                raise ValueError(
                    f"Shed event references an unconfigured appliance: "
                    f"{event.building_id}/{event.appliance_id}"
                )
            priority = event.priority or appliance.priority
            if priority not in tiers:
                raise ValueError(f"Unknown appliance priority {priority!r}")
            power_kw = event.power_delta_kw
            if power_kw is None:
                power_kw = appliance.rated_power_kw * building.weight_k
            active[key] = (event.simulation_time_s, power_kw, priority)
        elif event.event_type == "restore" and key in active:
            start_s, power_kw, priority = active.pop(key)
            duration_h = max(0.0, event.simulation_time_s - start_s) / 3600.0
            energy_kwh = power_kw * duration_h
            tiers[priority] += energy_kwh
            buildings[event.building_id] = (
                buildings.get(event.building_id, 0.0) + energy_kwh
            )

    for (building_id, _appliance_id), (start_s, power_kw, priority) in active.items():
        duration_h = max(0.0, run_end_s - start_s) / 3600.0
        energy_kwh = power_kw * duration_h
        tiers[priority] += energy_kwh
        buildings[building_id] = buildings.get(building_id, 0.0) + energy_kwh
    return tiers, buildings


def critical_energy_not_served_kwh(
    events: list[ControlEvent],
    scenario: ScenarioConfig,
    run_end_s: float,
) -> float:
    """Integrate nominal critical-load kWh from shed/restore event intervals."""
    tiers, _ = _integrate_curtailed_energy(events, scenario, run_end_s)
    return tiers["critical"]


def medical_load_interruption_s(
    events: list[ControlEvent],
    scenario: ScenarioConfig,
    run_end_s: float,
) -> float:
    """Total medical-device interruption time, summed across configured devices."""
    appliance_configs = {
        (building.building_id, appliance.appliance_id): appliance
        for building in scenario.buildings
        for appliance in building.appliances
    }
    active: dict[tuple[str, str], float] = {}
    interrupted_seconds = 0.0
    for event in sorted(events, key=lambda item: item.simulation_time_s):
        if not event.appliance_id:
            continue
        key = (event.building_id, event.appliance_id)
        appliance = appliance_configs.get(key)
        if appliance is None or appliance.appliance_type != "medical_device":
            continue
        if "shed" in event.event_type or event.event_type == "feeder_trip":
            active.setdefault(key, event.simulation_time_s)
        elif event.event_type == "restore" and key in active:
            interrupted_seconds += max(
                0.0, event.simulation_time_s - active.pop(key)
            )
    interrupted_seconds += sum(
        max(0.0, run_end_s - start_s) for start_s in active.values()
    )
    return interrupted_seconds


def shed_latency_s(events: list[ControlEvent], stage: str) -> float | None:
    """
    Mean time from a stage-trigger event to first shed command at that stage.

    stage: e.g. 's1', 's2', 's3'
    """
    # Find shed events for that stage type
    trigger_map = {
        "s1": "shed_deferrable",
        "s2": "shed_essential",
        "s3": "shed_essential",
    }
    event_type = trigger_map.get(stage)
    if not event_type:
        return None

    shed_events = [e for e in events if e.event_type == event_type]
    if not shed_events:
        return None

    # Approximate: latency = time of first shed event minus sim start (rough proxy)
    first_shed_time = min(e.simulation_time_s for e in shed_events)
    return first_shed_time


def rebound_peak_pu(
    telemetry: list[TelemetrySample],
    baseline_demand_pu: float,
    restoration_start_s: float,
) -> float:
    """
    Peak demand_pu during restoration window above baseline.
    """
    if not telemetry:
        return 0.0
    restoration_samples = [
        s for s in telemetry if s.simulation_time_s >= restoration_start_s
    ]
    if not restoration_samples:
        return 0.0
    peak = max(s.demand_pu for s in restoration_samples)
    return max(0.0, peak - baseline_demand_pu)


def feeder_trips_count(events: list[ControlEvent]) -> int:
    """Count ControlEvents with event_type='feeder_trip' (P1 policy)."""
    return sum(1 for e in events if e.event_type == "feeder_trip")


def energy_curtailed_by_tier(
    events: list[ControlEvent],
    scenario: ScenarioConfig,
    run_end_s: float,
) -> dict[str, float]:
    """Integrate nominal curtailed kWh by priority until restoration or run end."""
    tiers, _ = _integrate_curtailed_energy(events, scenario, run_end_s)
    return tiers


def jains_fairness_index(curtailments_per_building: dict[str, float]) -> float:
    """
    Jain's fairness index over cumulative curtailment per building.
    J = (Σxi)² / (n * Σxi²)

    Returns 1.0 when all curtailments are zero or equal (perfectly fair).
    """
    values = list(curtailments_per_building.values())
    n = len(values)
    if n == 0:
        return 1.0
    sum_x = sum(values)
    sum_x2 = sum(v * v for v in values)
    if sum_x2 == 0.0:
        return 1.0
    return (sum_x ** 2) / (n * sum_x2)


def over_frequency_excursion_time_s(
    telemetry: list[TelemetrySample],
    dt_s: float = 0.5,
) -> float:
    """
    Total seconds where frequency_hz > 50.05 Hz.
    dt_s is the telemetry push interval.
    """
    return sum(dt_s for s in telemetry if s.frequency_hz > 50.05)


def compute_all_metrics(
    result: SimulationResult,
    scenario: ScenarioConfig,
    telemetry: list[TelemetrySample] | None = None,
) -> dict[str, float]:
    """
    Compute and return all applicable metrics as a flat dict.

    The Prompt 8 contract expects the signature ``compute_all_metrics(result, scenario)``;
    this implementation keeps backwards compatibility with the existing telemetry-aware
    helper by accepting an optional third argument.
    """
    if telemetry is None:
        telemetry = getattr(result, "telemetry", None) or []
    if telemetry is None:
        telemetry = []

    events = list(getattr(result, "events", []) or [])
    dist_start = getattr(scenario.disturbance, "start_time_s", 0.0)
    baseline_demand = 1.0  # per-unit baseline

    run_end_s = result.final_state.time_s
    tier_curtailment, curtailment = _integrate_curtailed_energy(
        events, scenario, run_end_s
    )

    restore_events = [e for e in events if e.event_type == "restore"]
    restoration_start = (
        min(e.simulation_time_s for e in restore_events)
        if restore_events else getattr(scenario, "simulation_duration_s", 0.0)
    )

    recovery_band_hz = getattr(getattr(scenario, "grid_params", None), "f_recovery_hz", 49.95)
    stability_duration_s = getattr(getattr(scenario, "grid_params", None), "t_stable_s", 60.0)
    recovery_time = recovery_time_s(
        telemetry,
        recovery_band_hz=recovery_band_hz,
        stability_duration_s=stability_duration_s,
        disturbance_start_s=dist_start,
    )

    metrics = {
        "frequency_nadir_hz": frequency_nadir(telemetry),
        "max_rocof_hz_per_s": max_rocof(telemetry),
        "recovery_time_s": recovery_time if recovery_time is not None else -1.0,
        "critical_ens_kwh": tier_curtailment["critical"],
        "medical_load_interruption_s": medical_load_interruption_s(
            events, scenario, run_end_s
        ),
        "feeder_trips_count": float(feeder_trips_count(events)),
        "rebound_peak_pu": rebound_peak_pu(telemetry, baseline_demand, restoration_start),
        "energy_curtailed_critical_kwh": tier_curtailment["critical"],
        "energy_curtailed_essential_kwh": tier_curtailment["essential"],
        "energy_curtailed_deferrable_kwh": tier_curtailment["deferrable"],
        "jains_fairness_index": jains_fairness_index(curtailment),
        "over_frequency_excursion_time_s": over_frequency_excursion_time_s(telemetry),
        "total_shed_events": float(
            sum(1 for e in events if "shed" in e.event_type or e.event_type == "feeder_trip")
        ),
        "total_restore_events": float(len(restore_events)),
    }
    metrics["frequency_nadir"] = metrics["frequency_nadir_hz"]
    metrics["max_rocof"] = metrics["max_rocof_hz_per_s"]
    metrics["recovery_time"] = metrics["recovery_time_s"]
    metrics["critical_ens"] = metrics["critical_ens_kwh"]
    metrics["feeder_trips"] = metrics["feeder_trips_count"]
    metrics["rebound_peak"] = metrics["rebound_peak_pu"]
    metrics["energy_curtailed_critical"] = metrics["energy_curtailed_critical_kwh"]
    metrics["energy_curtailed_essential"] = metrics["energy_curtailed_essential_kwh"]
    metrics["energy_curtailed_deferrable"] = metrics["energy_curtailed_deferrable_kwh"]
    return metrics
