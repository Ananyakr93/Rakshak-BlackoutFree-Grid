"""Synthetic-only NILM event classification experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.nilm.detector import NILMEventDetector, make_synthetic_signal
from app.nilm.evaluation import evaluate_classification


def run_e9(seed: int = 42) -> dict[str, object]:
    labels = [
        "split_ac_1ton",
        "geyser_15l",
        "ceiling_fan",
        "ev_charger_car",
        "unknown",
    ]
    ratings = [1.0, 2.0, 0.075, 3.3, 5.7]
    samples = make_synthetic_signal(
        [(index * 2 + 1, rating) for index, rating in enumerate(ratings)],
        sample_count=12,
        sample_interval_s=1.0,
        noise_std_kw=0.005,
        seed=seed,
    )
    detected = NILMEventDetector().detect(samples)
    predicted = [
        event.appliance_type if event.classification == "classified" else None
        for event in detected
    ]
    evaluation = evaluate_classification(labels, predicted)
    return {
        "experiment": "E9",
        "seed": seed,
        "data_source": "synthetic aggregate active-power steps",
        "claim_boundary": (
            "Synthetic results evaluate the algorithm on generated signatures; "
            "they do not establish real-world NILM accuracy."
        ),
        "metrics": {
            "precision": evaluation.precision,
            "recall": evaluation.recall,
            "f1_score": evaluation.f1_score,
            "confusion_matrix": evaluation.confusion_matrix,
            "sample_count": evaluation.sample_count,
        },
        "raw_events": [
            {
                "expected": expected,
                "predicted": prediction,
                "confidence": event.confidence,
                "classification": event.classification,
                "features": event.features,
            }
            for expected, prediction, event in zip(
                labels, predicted, detected, strict=True
            )
        ],
    }


if __name__ == "__main__":
    output = Path(__file__).with_name("results_e9.json")
    output.write_text(json.dumps(run_e9(), indent=2), encoding="utf-8")
    print(f"E9 synthetic NILM results written to {output}")
