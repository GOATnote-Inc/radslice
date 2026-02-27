"""Human calibration loader and Cohen's kappa for judge validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CalibrationEntry:
    """A single human-graded calibration entry."""

    task_id: str
    dimension_scores: dict[str, float]
    failure_class: str | None
    grader_id: str = ""
    notes: str = ""


@dataclass(frozen=True)
class CalibrationResult:
    """Result of comparing judge grades to human calibration."""

    cohens_kappa: float
    percent_agreement: float
    per_dimension_correlation: dict[str, float]
    n_tasks: int
    confusion_matrix: dict[str, dict[str, int]]


def load_calibration(path: str | Path) -> list[CalibrationEntry]:
    """Load human calibration data from JSONL."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            entries.append(
                CalibrationEntry(
                    task_id=data["task_id"],
                    dimension_scores=data["dimension_scores"],
                    failure_class=data.get("failure_class"),
                    grader_id=data.get("grader_id", ""),
                    notes=data.get("notes", ""),
                )
            )
    return entries


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Compute Cohen's kappa between two sets of categorical labels.

    kappa >= 0.60 is moderate-to-substantial agreement.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("Label lists must be same length")
    n = len(labels_a)
    if n == 0:
        return 0.0

    # Get all unique categories
    categories = sorted(set(labels_a) | set(labels_b))
    cat_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    # Build confusion matrix
    matrix = [[0] * k for _ in range(k)]
    for a, b in zip(labels_a, labels_b):
        matrix[cat_idx[a]][cat_idx[b]] += 1

    # Observed agreement
    p_o = sum(matrix[i][i] for i in range(k)) / n

    # Expected agreement
    p_e = 0.0
    for i in range(k):
        row_sum = sum(matrix[i])
        col_sum = sum(matrix[j][i] for j in range(k))
        p_e += (row_sum * col_sum) / (n * n)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def compute_calibration(
    human_entries: list[CalibrationEntry],
    judge_entries: list[CalibrationEntry],
) -> CalibrationResult:
    """Compare judge grades to human calibration grades."""
    # Match by task_id
    human_by_id = {e.task_id: e for e in human_entries}
    judge_by_id = {e.task_id: e for e in judge_entries}
    common_ids = sorted(set(human_by_id) & set(judge_by_id))

    if not common_ids:
        return CalibrationResult(
            cohens_kappa=0.0,
            percent_agreement=0.0,
            per_dimension_correlation={},
            n_tasks=0,
            confusion_matrix={},
        )

    # Failure class agreement
    human_classes = []
    judge_classes = []
    for tid in common_ids:
        hc = human_by_id[tid].failure_class or "PASS"
        jc = judge_by_id[tid].failure_class or "PASS"
        human_classes.append(hc)
        judge_classes.append(jc)

    kappa = cohens_kappa(human_classes, judge_classes)
    agree = sum(1 for h, j in zip(human_classes, judge_classes) if h == j)
    pct_agree = agree / len(common_ids)

    # Per-dimension Pearson correlation
    dim_names = [
        "diagnostic_accuracy",
        "finding_detection",
        "anatomic_precision",
        "clinical_relevance",
        "false_positive_control",
    ]
    dim_corr = {}
    for dim in dim_names:
        h_vals = [human_by_id[tid].dimension_scores.get(dim, 0.0) for tid in common_ids]
        j_vals = [judge_by_id[tid].dimension_scores.get(dim, 0.0) for tid in common_ids]
        dim_corr[dim] = _pearson(h_vals, j_vals)

    # Confusion matrix
    categories = sorted(set(human_classes) | set(judge_classes))
    conf = {c: {cc: 0 for cc in categories} for c in categories}
    for h, j in zip(human_classes, judge_classes):
        conf[h][j] += 1

    return CalibrationResult(
        cohens_kappa=kappa,
        percent_agreement=pct_agree,
        per_dimension_correlation=dim_corr,
        n_tasks=len(common_ids),
        confusion_matrix=conf,
    )


def _pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    sy = sum((yi - my) ** 2 for yi in y) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)
