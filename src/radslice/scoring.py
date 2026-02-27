"""Scoring: pass@k, pass^k, Wilson CI, bootstrap CI, and aggregate metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AggregateScore:
    """Aggregate evaluation score with confidence intervals."""

    pass_at_k: float  # P(>=1 of k trials passes)
    pass_pow_k: float  # P(all k trials pass)
    accuracy: float
    finding_recall: float
    false_positive_rate: float
    total_tasks: int
    total_trials: int
    wilson_ci: tuple[float, float] = (0.0, 1.0)
    bootstrap_ci: tuple[float, float] = (0.0, 1.0)
    per_modality: dict[str, float] = field(default_factory=dict)
    per_anatomy: dict[str, float] = field(default_factory=dict)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion.

    Valid for small n (unlike normal approximation).
    Returns (lower, upper) clamped to [0, 1].
    """
    if n == 0:
        return (0.0, 1.0)
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * n)) / n) / denom
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


def bootstrap_ci(
    values: list[bool],
    n_iterations: int = 10_000,
    percentiles: tuple[float, float] = (2.5, 97.5),
    rng_seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap confidence interval on binary values.

    Resamples with replacement, returns percentile bounds.
    """
    import random

    if not values:
        return (0.0, 1.0)

    rng = random.Random(rng_seed)
    n = len(values)
    means = []
    for _ in range(n_iterations):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()

    lo_idx = int(percentiles[0] / 100 * len(means))
    hi_idx = int(percentiles[1] / 100 * len(means)) - 1
    lo_idx = max(0, min(lo_idx, len(means) - 1))
    hi_idx = max(0, min(hi_idx, len(means) - 1))
    return (means[lo_idx], means[hi_idx])


def pass_at_k(trial_results: list[bool]) -> bool:
    """pass@k: True if at least one of k trials passed."""
    return any(trial_results)


def pass_pow_k(trial_results: list[bool]) -> bool:
    """pass^k: True if ALL k trials passed. Deployment gate metric."""
    return all(trial_results)


def compute_pass_at_k_rate(scenario_trials: list[list[bool]]) -> float:
    """Compute pass@k rate across scenarios. Each inner list is k trial results."""
    if not scenario_trials:
        return 0.0
    passed = sum(1 for trials in scenario_trials if pass_at_k(trials))
    return passed / len(scenario_trials)


def compute_pass_pow_k_rate(scenario_trials: list[list[bool]]) -> float:
    """Compute pass^k rate across scenarios."""
    if not scenario_trials:
        return 0.0
    passed = sum(1 for trials in scenario_trials if pass_pow_k(trials))
    return passed / len(scenario_trials)


def compute_accuracy(correct: int, total: int) -> float:
    """Simple accuracy: correct / total."""
    if total == 0:
        return 0.0
    return correct / total


def compute_finding_recall(detected_findings: int, total_required_findings: int) -> float:
    """Recall of required findings."""
    if total_required_findings == 0:
        return 1.0
    return detected_findings / total_required_findings


def compute_false_positive_rate(false_positives: int, total_tasks: int) -> float:
    """Rate of tasks with false-positive overcalls."""
    if total_tasks == 0:
        return 0.0
    return false_positives / total_tasks


def two_proportion_z_test(s1: int, n1: int, s2: int, n2: int) -> tuple[float, bool]:
    """Two-proportion z-test. Returns (z_stat, is_regression).

    Regression flagged if z < -1.96 (one-tailed).
    s1/n1 = current, s2/n2 = prior.
    """
    if n1 == 0 or n2 == 0:
        return (0.0, False)
    p1 = s1 / n1
    p2 = s2 / n2
    p_pool = (s1 + s2) / (n1 + n2)
    if p_pool == 0.0 or p_pool == 1.0:
        return (0.0, False)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, False)
    z = (p1 - p2) / se
    return (z, z < -1.96)
