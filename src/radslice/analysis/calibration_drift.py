"""Calibration drift detection: monitor grading consistency over time."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from radslice.grading.calibration import (
    CalibrationEntry,
    CalibrationResult,
    cohens_kappa,
    compute_calibration,
    load_calibration,
)


@dataclass(frozen=True)
class DriftReport:
    """Calibration drift analysis report."""

    layer0_vs_layer2_agreement: float
    layer0_vs_layer2_kappa: float
    per_modality: dict[str, dict[str, float]]  # modality -> {agreement, kappa}
    drift_detected: bool  # True if kappa < threshold or agreement < min_agreement
    kappa_threshold: float
    agreement_threshold: float
    total_grades: int
    human_comparison: CalibrationResult | None  # None if no human grades


def _infer_modality(task_id: str) -> str:
    """Infer modality from task ID prefix."""
    prefix = task_id.split("-")[0].lower()
    modality_map = {"xray": "xray", "ct": "ct", "mri": "mri", "us": "ultrasound"}
    return modality_map.get(prefix, "unknown")


def compute_calibration_drift(
    grades: list[dict],
    calibration_set_ids: set[str] | None = None,
    kappa_threshold: float = 0.60,
    agreement_threshold: float = 0.70,
) -> DriftReport:
    """Compute calibration drift from grades with Layer 0 and Layer 2 results.

    Compares Layer 0 (pattern) and Layer 2 (LLM judge) failure classifications
    for grades that have both layers.

    Args:
        grades: List of grade dicts with detection_layer, failure_class fields.
        calibration_set_ids: Optional set of task IDs to restrict analysis to.
        kappa_threshold: Minimum Cohen's kappa (default 0.60).
        agreement_threshold: Minimum percent agreement (default 0.70).

    Returns:
        DriftReport with agreement metrics and drift detection.
    """
    # Filter to calibration set if specified
    if calibration_set_ids:
        grades = [g for g in grades if g.get("task_id", "") in calibration_set_ids]

    if not grades:
        return DriftReport(
            layer0_vs_layer2_agreement=0.0,
            layer0_vs_layer2_kappa=0.0,
            per_modality={},
            drift_detected=False,
            kappa_threshold=kappa_threshold,
            agreement_threshold=agreement_threshold,
            total_grades=0,
            human_comparison=None,
        )

    # Extract Layer 0 and Layer 2 failure classifications
    # Grades have pattern_result and judge_result fields
    layer0_labels: list[str] = []
    layer2_labels: list[str] = []
    modality_labels: dict[str, tuple[list[str], list[str]]] = {}

    for g in grades:
        # Get pattern (Layer 0) assessment
        pattern_result = g.get("pattern_result", {})
        judge_result = g.get("judge_result", {})

        # Skip grades without both layers
        if not pattern_result or not judge_result:
            continue

        # Layer 0: pass if all_required_pass, else failure class from patterns
        l0_class = "PASS" if pattern_result.get("all_required_pass", False) else "FAIL"

        # Layer 2: pass if no failure_class from judge
        l2_failure = judge_result.get("failure_class")
        l2_class = l2_failure if l2_failure else "PASS"

        layer0_labels.append(l0_class)
        layer2_labels.append(l2_class)

        # Per-modality tracking
        mod = _infer_modality(g.get("task_id", ""))
        if mod not in modality_labels:
            modality_labels[mod] = ([], [])
        modality_labels[mod][0].append(l0_class)
        modality_labels[mod][1].append(l2_class)

    if not layer0_labels:
        return DriftReport(
            layer0_vs_layer2_agreement=0.0,
            layer0_vs_layer2_kappa=0.0,
            per_modality={},
            drift_detected=False,
            kappa_threshold=kappa_threshold,
            agreement_threshold=agreement_threshold,
            total_grades=len(grades),
            human_comparison=None,
        )

    # Compute overall agreement
    agreement = sum(1 for a, b in zip(layer0_labels, layer2_labels) if a == b) / len(layer0_labels)

    kappa = cohens_kappa(layer0_labels, layer2_labels)

    # Per-modality
    per_modality: dict[str, dict[str, float]] = {}
    for mod, (l0, l2) in modality_labels.items():
        if l0:
            mod_agree = sum(1 for a, b in zip(l0, l2) if a == b) / len(l0)
            mod_kappa = cohens_kappa(l0, l2)
            per_modality[mod] = {"agreement": mod_agree, "kappa": mod_kappa}

    drift = kappa < kappa_threshold or agreement < agreement_threshold

    return DriftReport(
        layer0_vs_layer2_agreement=agreement,
        layer0_vs_layer2_kappa=kappa,
        per_modality=per_modality,
        drift_detected=drift,
        kappa_threshold=kappa_threshold,
        agreement_threshold=agreement_threshold,
        total_grades=len(grades),
        human_comparison=None,
    )


def compare_to_human(
    human_grades_path: str | Path,
    judge_grades: list[dict],
) -> CalibrationResult | None:
    """Compare judge grades to physician reference grades.

    Args:
        human_grades_path: Path to human_grades.jsonl.
        judge_grades: List of grade dicts from the judge.

    Returns:
        CalibrationResult or None if no human grades available.
    """
    path = Path(human_grades_path)
    if not path.exists() or path.stat().st_size == 0:
        return None

    human_entries = load_calibration(path)
    if not human_entries:
        return None

    # Convert judge grades to CalibrationEntry format
    judge_entries = []
    for g in judge_grades:
        dim_scores = g.get("dimension_scores", {})
        if not dim_scores:
            continue
        judge_entries.append(
            CalibrationEntry(
                task_id=g.get("task_id", ""),
                dimension_scores=dim_scores,
                failure_class=g.get("failure_class"),
                grader_id="judge",
            )
        )

    if not judge_entries:
        return None

    return compute_calibration(human_entries, judge_entries)


def format_drift_report(report: DriftReport) -> str:
    """Format drift report as markdown."""
    lines = [
        "# Calibration Drift Report",
        "",
        f"- **Total grades analyzed:** {report.total_grades}",
        f"- **Layer 0 vs Layer 2 agreement:** {report.layer0_vs_layer2_agreement:.1%}",
        f"- **Cohen's kappa:** {report.layer0_vs_layer2_kappa:.3f}",
        f"- **Drift detected:** {'YES' if report.drift_detected else 'No'}",
        f"- **Thresholds:** kappa >= {report.kappa_threshold}, "
        f"agreement >= {report.agreement_threshold:.0%}",
        "",
    ]

    if report.per_modality:
        lines.append("## Per-Modality Breakdown")
        lines.append("")
        lines.append("| Modality | Agreement | Kappa |")
        lines.append("|----------|-----------|-------|")
        for mod, data in sorted(report.per_modality.items()):
            lines.append(f"| {mod} | {data['agreement']:.1%} | {data['kappa']:.3f} |")
        lines.append("")

    if report.human_comparison:
        hc = report.human_comparison
        lines.append("## Human Comparison")
        lines.append("")
        lines.append(f"- **Cohen's kappa (vs human):** {hc.cohens_kappa:.3f}")
        lines.append(f"- **Agreement (vs human):** {hc.percent_agreement:.1%}")
        lines.append(f"- **Tasks compared:** {hc.n_tasks}")
        lines.append("")

    return "\n".join(lines)
