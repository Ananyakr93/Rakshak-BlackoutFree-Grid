"""Metrics for synthetic and measured NILM event-classification evaluations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NILMEvaluation:
    precision: float
    recall: float
    f1_score: float
    confusion_matrix: dict[str, dict[str, int]]
    sample_count: int


def evaluate_classification(expected: list[str], predicted: list[str | None]) -> NILMEvaluation:
    """Return micro-averaged precision/recall/F1 and a class confusion matrix."""
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted labels must have equal lengths")
    labels = sorted(set(expected) | {value or "unknown" for value in predicted})
    matrix = {actual: {guess: 0 for guess in labels} for actual in labels}
    for actual, guess in zip(expected, predicted, strict=True):
        matrix[actual][guess or "unknown"] += 1
    true_positive = sum(matrix[label][label] for label in labels if label != "unknown")
    predicted_positive = sum(
        matrix[actual][guess] for actual in labels for guess in labels if guess != "unknown"
    )
    actual_positive = sum(
        matrix[actual][guess] for actual in labels if actual != "unknown" for guess in labels
    )
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / actual_positive if actual_positive else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return NILMEvaluation(
        precision=precision,
        recall=recall,
        f1_score=f1,
        confusion_matrix=matrix,
        sample_count=len(expected),
    )
