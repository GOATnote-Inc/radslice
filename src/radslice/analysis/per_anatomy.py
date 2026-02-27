"""Per-anatomy breakdowns of evaluation results."""

from __future__ import annotations

from radslice.scoring import wilson_ci


def anatomy_breakdown(grades: list[dict]) -> dict[str, dict]:
    """Compute per-anatomy metrics from grade dicts."""
    by_anatomy: dict[str, list[dict]] = {}
    for g in grades:
        anatomy = g.get("metadata", {}).get("anatomy", "unknown")
        by_anatomy.setdefault(anatomy, []).append(g)

    results = {}
    for anatomy, anat_grades in sorted(by_anatomy.items()):
        n_passed = sum(1 for g in anat_grades if g.get("passed"))
        n_total = len(anat_grades)
        wci = wilson_ci(n_passed, n_total)

        # Per-dimension means
        dim_sums: dict[str, float] = {}
        dim_counts: dict[str, int] = {}
        for g in anat_grades:
            for dim, score in g.get("dimension_scores", {}).items():
                dim_sums[dim] = dim_sums.get(dim, 0.0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1

        dim_means = {
            dim: dim_sums[dim] / dim_counts[dim] for dim in dim_sums if dim_counts[dim] > 0
        }

        results[anatomy] = {
            "total_grades": n_total,
            "passed": n_passed,
            "pass_rate": n_passed / n_total if n_total > 0 else 0.0,
            "wilson_ci": wci,
            "dimension_means": dim_means,
        }

    return results
