"""Tests for scoring.py — pass@k, pass^k, Wilson CI, bootstrap CI."""

from __future__ import annotations

import pytest

from radslice.scoring import (
    bootstrap_ci,
    compute_accuracy,
    compute_false_positive_rate,
    compute_finding_recall,
    compute_pass_at_k_rate,
    compute_pass_pow_k_rate,
    pass_at_k,
    pass_pow_k,
    two_proportion_z_test,
    wilson_ci,
)

# --- pass@k ---


class TestPassAtK:
    def test_all_pass(self):
        assert pass_at_k([True, True, True]) is True

    def test_one_pass(self):
        assert pass_at_k([False, True, False]) is True

    def test_all_fail(self):
        assert pass_at_k([False, False, False]) is False

    def test_single_pass(self):
        assert pass_at_k([True]) is True

    def test_single_fail(self):
        assert pass_at_k([False]) is False

    def test_empty(self):
        assert pass_at_k([]) is False


# --- pass^k ---


class TestPassPowK:
    def test_all_pass(self):
        assert pass_pow_k([True, True, True]) is True

    def test_one_fail(self):
        assert pass_pow_k([True, False, True]) is False

    def test_all_fail(self):
        assert pass_pow_k([False, False, False]) is False

    def test_single_pass(self):
        assert pass_pow_k([True]) is True

    def test_single_fail(self):
        assert pass_pow_k([False]) is False

    def test_empty(self):
        assert pass_pow_k([]) is True  # vacuously true


# --- Wilson CI ---


class TestWilsonCI:
    def test_perfect_score(self):
        lo, hi = wilson_ci(10, 10)
        assert lo > 0.6
        assert hi == 1.0

    def test_zero_score(self):
        lo, hi = wilson_ci(0, 10)
        assert lo == 0.0
        assert hi < 0.4

    def test_half_score(self):
        lo, hi = wilson_ci(50, 100)
        assert 0.35 < lo < 0.50
        assert 0.50 < hi < 0.65

    def test_single_success(self):
        lo, hi = wilson_ci(1, 1)
        assert lo > 0.0
        assert hi == 1.0

    def test_empty(self):
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 1.0

    def test_bounds_clamped(self):
        lo, hi = wilson_ci(5, 10)
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0
        assert lo <= hi

    def test_small_n(self):
        # n=5 should still give valid bounds
        lo, hi = wilson_ci(3, 5)
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0

    def test_large_n_narrows(self):
        lo5, hi5 = wilson_ci(3, 5)
        lo100, hi100 = wilson_ci(60, 100)
        # CI should be narrower with larger n
        assert (hi100 - lo100) < (hi5 - lo5)


# --- Bootstrap CI ---


class TestBootstrapCI:
    def test_all_true(self):
        lo, hi = bootstrap_ci([True] * 20)
        assert lo == 1.0
        assert hi == 1.0

    def test_all_false(self):
        lo, hi = bootstrap_ci([False] * 20)
        assert lo == 0.0
        assert hi == 0.0

    def test_mixed(self):
        values = [True] * 7 + [False] * 3
        lo, hi = bootstrap_ci(values)
        assert 0.3 < lo < 0.8
        assert 0.7 <= hi <= 1.0

    def test_empty(self):
        lo, hi = bootstrap_ci([])
        assert lo == 0.0
        assert hi == 1.0

    def test_deterministic(self):
        values = [True, False, True, True, False]
        ci1 = bootstrap_ci(values, rng_seed=42)
        ci2 = bootstrap_ci(values, rng_seed=42)
        assert ci1 == ci2

    def test_different_seeds(self):
        values = [True, False] * 10
        ci1 = bootstrap_ci(values, rng_seed=42)
        ci2 = bootstrap_ci(values, rng_seed=123)
        # May differ slightly due to different resampling
        assert isinstance(ci1, tuple) and isinstance(ci2, tuple)


# --- Aggregate rates ---


class TestAggregateRates:
    def test_pass_at_k_rate(self):
        scenarios = [
            [True, True, True],
            [False, True, False],
            [False, False, False],
        ]
        rate = compute_pass_at_k_rate(scenarios)
        assert rate == pytest.approx(2 / 3)

    def test_pass_pow_k_rate(self):
        scenarios = [
            [True, True, True],
            [False, True, False],
            [False, False, False],
        ]
        rate = compute_pass_pow_k_rate(scenarios)
        assert rate == pytest.approx(1 / 3)

    def test_empty_scenarios(self):
        assert compute_pass_at_k_rate([]) == 0.0
        assert compute_pass_pow_k_rate([]) == 0.0

    def test_all_pass(self):
        scenarios = [[True, True]] * 5
        assert compute_pass_at_k_rate(scenarios) == 1.0
        assert compute_pass_pow_k_rate(scenarios) == 1.0

    def test_all_fail(self):
        scenarios = [[False, False]] * 5
        assert compute_pass_at_k_rate(scenarios) == 0.0
        assert compute_pass_pow_k_rate(scenarios) == 0.0


# --- Simple metrics ---


class TestSimpleMetrics:
    def test_accuracy(self):
        assert compute_accuracy(8, 10) == pytest.approx(0.8)

    def test_accuracy_zero(self):
        assert compute_accuracy(0, 0) == 0.0

    def test_finding_recall(self):
        assert compute_finding_recall(4, 5) == pytest.approx(0.8)

    def test_finding_recall_none_required(self):
        assert compute_finding_recall(0, 0) == 1.0

    def test_false_positive_rate(self):
        assert compute_false_positive_rate(3, 10) == pytest.approx(0.3)

    def test_false_positive_rate_zero(self):
        assert compute_false_positive_rate(0, 0) == 0.0


# --- Two-proportion z-test ---


class TestTwoProportionZTest:
    def test_no_regression(self):
        z, is_reg = two_proportion_z_test(8, 10, 7, 10)
        assert is_reg is False

    def test_regression(self):
        z, is_reg = two_proportion_z_test(2, 100, 80, 100)
        assert is_reg is True
        assert z < -1.96

    def test_equal(self):
        z, is_reg = two_proportion_z_test(5, 10, 5, 10)
        assert z == pytest.approx(0.0)
        assert is_reg is False

    def test_empty(self):
        z, is_reg = two_proportion_z_test(0, 0, 5, 10)
        assert z == 0.0
        assert is_reg is False

    def test_perfect_scores(self):
        z, is_reg = two_proportion_z_test(10, 10, 10, 10)
        assert is_reg is False

    def test_zero_scores(self):
        z, is_reg = two_proportion_z_test(0, 10, 0, 10)
        assert is_reg is False
