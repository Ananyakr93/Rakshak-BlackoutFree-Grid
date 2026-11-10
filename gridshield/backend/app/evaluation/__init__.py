"""
Evaluation engine for GridShield experiments.

Contains metric computations and the ExperimentRunner that executes
the same scenario under multiple policies and seeds, collecting
paired comparisons with confidence intervals.
"""

from app.evaluation.experiments import ExperimentResult, ExperimentRunner, PolicySummary
from app.evaluation.metrics import (
    compute_all_metrics,
    critical_energy_not_served_kwh,
    energy_curtailed_by_tier,
    feeder_trips_count,
    frequency_nadir,
    jains_fairness_index,
    max_rocof,
    over_frequency_excursion_time_s,
    rebound_peak_pu,
    recovery_time_s,
    shed_latency_s,
)

__all__ = [
    "ExperimentResult",
    "ExperimentRunner",
    "PolicySummary",
    "compute_all_metrics",
    "critical_energy_not_served_kwh",
    "energy_curtailed_by_tier",
    "feeder_trips_count",
    "frequency_nadir",
    "jains_fairness_index",
    "max_rocof",
    "over_frequency_excursion_time_s",
    "rebound_peak_pu",
    "recovery_time_s",
    "shed_latency_s",
]
