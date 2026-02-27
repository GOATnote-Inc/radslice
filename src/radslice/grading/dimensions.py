"""5 grading dimensions with weights for radiology evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GradingDimension:
    """A single grading dimension with weight and description."""

    name: str
    weight: float
    description: str
    scale_min: float = 0.0
    scale_max: float = 1.0


DIMENSIONS = [
    GradingDimension(
        name="diagnostic_accuracy",
        weight=0.35,
        description="Correct primary diagnosis and appropriate differential",
    ),
    GradingDimension(
        name="finding_detection",
        weight=0.25,
        description="Required findings identified with correct locations",
    ),
    GradingDimension(
        name="anatomic_precision",
        weight=0.15,
        description="Correct laterality, lobe, segment, or anatomic reference",
    ),
    GradingDimension(
        name="clinical_relevance",
        weight=0.15,
        description="Appropriate severity assessment and clinical recommendations",
    ),
    GradingDimension(
        name="false_positive_control",
        weight=0.10,
        description="No hallucinated pathology or overcalled findings",
    ),
]


def weighted_score(dimension_scores: dict[str, float]) -> float:
    """Compute weighted aggregate score from dimension scores."""
    total = 0.0
    weight_sum = 0.0
    for dim in DIMENSIONS:
        if dim.name in dimension_scores:
            total += dim.weight * dimension_scores[dim.name]
            weight_sum += dim.weight
    if weight_sum == 0:
        return 0.0
    return total / weight_sum
