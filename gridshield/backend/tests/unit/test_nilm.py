from __future__ import annotations

import pytest

from app.nilm.detector import (
    AggregatePowerSample,
    NILMEventDetector,
    NILMStateEstimator,
    make_synthetic_signal,
)
from app.nilm.evaluation import evaluate_classification
from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin


def test_detects_and_classifies_synthetic_switching_events():
    signal = make_synthetic_signal(
        [(1, 1.0), (3, -1.0)],
        sample_count=5,
        sample_interval_s=0.5,
        seed=7,
    )
    events = NILMEventDetector().detect(signal)

    assert [event.event_type for event in events] == ["switch_on", "switch_off"]
    assert [event.appliance_type for event in events] == [
        "split_ac_1ton",
        "split_ac_1ton",
    ]
    assert all(event.confidence == pytest.approx(1.0) for event in events)


def test_unknown_and_ambiguous_events_are_not_forced_into_a_class():
    ambiguous = NILMEventDetector(
        signatures_kw={"load_a": 1.0, "load_b": 1.0},
    ).detect(
        [
            AggregatePowerSample(0.0, 0.0),
            AggregatePowerSample(1.0, 1.0),
        ]
    )[0]
    unknown = NILMEventDetector().detect(
        [
            AggregatePowerSample(0.0, 0.0),
            AggregatePowerSample(1.0, 10.0),
        ]
    )[0]

    assert ambiguous.classification == "ambiguous"
    assert ambiguous.appliance_type is None
    assert unknown.classification == "unknown"
    assert unknown.appliance_type is None


def test_state_estimates_do_not_mutate_ground_truth_appliances():
    appliance = Appliance(
        "B1_AC",
        "B1",
        "split_ac_1ton",
        "deferrable",
        1.0,
        initial_state=ApplianceState.OFF,
    )
    building = BuildingTwin("B1", appliances=[appliance])
    event = NILMEventDetector().detect(
        [
            AggregatePowerSample(0.0, 0.0),
            AggregatePowerSample(1.0, 1.0),
        ]
    )

    estimates = NILMStateEstimator().apply(event, building)

    assert estimates[0].estimated_state == "ON"
    assert estimates[0].source == "nilm_estimate"
    assert appliance.state == ApplianceState.OFF


def test_evaluation_returns_confusion_matrix_and_micro_metrics():
    result = evaluate_classification(
        ["ac", "fan", "fan"],
        ["ac", "unknown", "fan"],
    )

    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1_score == pytest.approx(0.8)
    assert result.confusion_matrix["fan"]["unknown"] == 1


def test_samples_require_increasing_simulation_time():
    with pytest.raises(ValueError, match="increasing"):
        NILMEventDetector().detect(
            [
                AggregatePowerSample(1.0, 0.0),
                AggregatePowerSample(1.0, 1.0),
            ]
        )
