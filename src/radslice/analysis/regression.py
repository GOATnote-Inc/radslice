"""Version-to-version regression detection using two-proportion z-test."""

from __future__ import annotations

from dataclasses import dataclass, field

from radslice.scoring import two_proportion_z_test, wilson_ci


@dataclass(frozen=True)
class RegressionResult:
    """Result of regression detection between two runs."""

    overall_regression: bool
    regressed_modalities: list[str]
    z_scores: dict[str, float]
    current_rates: dict[str, float]
    prior_rates: dict[str, float]
    details: dict[str, dict] = field(default_factory=dict)


def detect_regression(
    current_grades: list[dict],
    prior_grades: list[dict],
) -> dict:
    """Detect per-modality regression between two runs.

    Returns regression info as a dict for JSON serialization.
    """
    current_by_mod = _modality_pass_counts(current_grades)
    prior_by_mod = _modality_pass_counts(prior_grades)

    all_mods = sorted(set(current_by_mod) | set(prior_by_mod))
    regressed = []
    z_scores = {}
    current_rates = {}
    prior_rates = {}
    details = {}

    for mod in all_mods:
        c_pass, c_total = current_by_mod.get(mod, (0, 0))
        p_pass, p_total = prior_by_mod.get(mod, (0, 0))

        if c_total == 0 or p_total == 0:
            continue

        z, is_reg = two_proportion_z_test(c_pass, c_total, p_pass, p_total)
        z_scores[mod] = round(z, 3)
        current_rates[mod] = round(c_pass / c_total, 3) if c_total > 0 else 0.0
        prior_rates[mod] = round(p_pass / p_total, 3) if p_total > 0 else 0.0

        if is_reg:
            regressed.append(mod)

        details[mod] = {
            "current": {
                "passed": c_pass,
                "total": c_total,
                "wilson_ci": wilson_ci(c_pass, c_total),
            },
            "prior": {"passed": p_pass, "total": p_total, "wilson_ci": wilson_ci(p_pass, p_total)},
            "z_score": round(z, 3),
            "regression": is_reg,
        }

    return {
        "overall_regression": len(regressed) > 0,
        "regressed_modalities": regressed,
        "z_scores": z_scores,
        "current_rates": current_rates,
        "prior_rates": prior_rates,
        "details": details,
    }


def _modality_pass_counts(grades: list[dict]) -> dict[str, tuple[int, int]]:
    """Return {modality: (passed, total)} from grade dicts."""
    counts: dict[str, list[int]] = {}  # mod -> [passed, total]
    for g in grades:
        mod = g.get("metadata", {}).get("modality", _infer_modality(g.get("task_id", "")))
        if mod not in counts:
            counts[mod] = [0, 0]
        counts[mod][1] += 1
        if g.get("passed"):
            counts[mod][0] += 1
    return {mod: (c[0], c[1]) for mod, c in counts.items()}


def _infer_modality(task_id: str) -> str:
    prefix = task_id.split("-")[0].lower()
    mapping = {"xray": "xray", "ct": "ct", "mri": "mri", "us": "ultrasound"}
    return mapping.get(prefix, "unknown")
