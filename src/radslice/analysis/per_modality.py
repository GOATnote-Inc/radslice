"""Per-modality breakdowns of evaluation results."""

from __future__ import annotations

from radslice.scoring import (
    compute_pass_at_k_rate,
    compute_pass_pow_k_rate,
    wilson_ci,
)


def modality_breakdown(grades: list[dict]) -> dict[str, dict]:
    """Compute per-modality metrics from grade dicts.

    Returns dict of modality -> {pass_rate, pass_at_k, pass_pow_k, wilson_ci, ...}
    """
    # Group grades by (modality, task_id, model)
    by_modality: dict[str, list[dict]] = {}
    for g in grades:
        mod = g.get("metadata", {}).get("modality", _infer_modality(g.get("task_id", "")))
        by_modality.setdefault(mod, []).append(g)

    results = {}
    for modality, mod_grades in sorted(by_modality.items()):
        # Group by (task_id, model) for trial aggregation
        trial_groups = _group_trials(mod_grades)
        scenario_trials = list(trial_groups.values())

        n_passed = sum(1 for g in mod_grades if g.get("passed"))
        n_total = len(mod_grades)

        # Failure class distribution
        failure_counts: dict[str, int] = {}
        for g in mod_grades:
            fc = g.get("failure_class")
            if fc:
                failure_counts[fc] = failure_counts.get(fc, 0) + 1

        wci = wilson_ci(n_passed, n_total)

        results[modality] = {
            "total_grades": n_total,
            "passed": n_passed,
            "pass_rate": n_passed / n_total if n_total > 0 else 0.0,
            "pass_at_k": compute_pass_at_k_rate(scenario_trials),
            "pass_pow_k": compute_pass_pow_k_rate(scenario_trials),
            "wilson_ci": wci,
            "failure_classes": failure_counts,
            "mean_score": (
                sum(g.get("weighted_score", 0) for g in mod_grades) / n_total
                if n_total > 0
                else 0.0
            ),
        }

    return results


def _infer_modality(task_id: str) -> str:
    """Infer modality from task ID prefix."""
    prefix = task_id.split("-")[0].lower()
    mapping = {"xray": "xray", "ct": "ct", "mri": "mri", "us": "ultrasound"}
    return mapping.get(prefix, "unknown")


def _group_trials(grades: list[dict]) -> dict[str, list[bool]]:
    """Group grades by (task_id, model) and extract trial pass/fail."""
    groups: dict[str, list[bool]] = {}
    for g in grades:
        key = f"{g.get('task_id')}:{g.get('model')}"
        groups.setdefault(key, []).append(bool(g.get("passed")))
    return groups
