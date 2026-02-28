"""Tests for calibration drift detection module."""

import json

from radslice.analysis.calibration_drift import (
    DriftReport,
    compare_to_human,
    compute_calibration_drift,
    format_drift_report,
)


def _make_grade(task_id, pattern_pass=True, judge_fail_class=None):
    """Create a grade dict with both pattern and judge results."""
    return {
        "task_id": task_id,
        "model": "gpt-5.2",
        "passed": pattern_pass and judge_fail_class is None,
        "pattern_result": {
            "all_required_pass": pattern_pass,
            "confidence": 0.9 if pattern_pass else 0.1,
        },
        "judge_result": {
            "failure_class": judge_fail_class,
        },
        "dimension_scores": {
            "diagnostic_accuracy": 0.8 if pattern_pass else 0.2,
            "finding_detection": 0.7,
        },
        "failure_class": judge_fail_class,
    }


class TestComputeCalibrationDrift:
    """Test calibration drift computation."""

    def test_empty_grades(self):
        report = compute_calibration_drift([])
        assert report.total_grades == 0
        assert report.drift_detected is False

    def test_perfect_agreement(self):
        """Layer 0 and Layer 2 agree perfectly (both pass or both fail)."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class=None),  # L0=PASS, L2=PASS
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class=None),  # L0=PASS, L2=PASS
        ]
        report = compute_calibration_drift(grades)
        assert report.layer0_vs_layer2_agreement == 1.0
        assert report.drift_detected is False

    def test_total_disagreement(self):
        """Layer 0 passes but Layer 2 fails everything."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class="A"),
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class="B"),
            _make_grade("CT-001", pattern_pass=True, judge_fail_class="A"),
        ]
        report = compute_calibration_drift(grades)
        assert report.layer0_vs_layer2_agreement == 0.0
        assert report.drift_detected is True

    def test_partial_agreement(self):
        """Mixed agreement."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class=None),  # agree
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class="A"),  # disagree
            _make_grade("CT-001", pattern_pass=False, judge_fail_class="B"),
        ]
        report = compute_calibration_drift(grades)
        # 1 agree (XRAY-001), 1 disagree (XRAY-002), 1 partial (CT-001 FAIL vs B)
        assert 0.0 < report.layer0_vs_layer2_agreement < 1.0

    def test_calibration_set_filter(self):
        """Only grades in calibration set are analyzed."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class=None),
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class="A"),
            _make_grade("CT-001", pattern_pass=True, judge_fail_class=None),
        ]
        # Only analyze XRAY-001 (perfect agreement)
        report = compute_calibration_drift(grades, calibration_set_ids={"XRAY-001"})
        assert report.layer0_vs_layer2_agreement == 1.0

    def test_per_modality_breakdown(self):
        """Per-modality metrics are computed."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class=None),
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class=None),
            _make_grade("CT-001", pattern_pass=True, judge_fail_class="A"),
        ]
        report = compute_calibration_drift(grades)
        assert "xray" in report.per_modality
        assert "ct" in report.per_modality
        assert report.per_modality["xray"]["agreement"] == 1.0
        assert report.per_modality["ct"]["agreement"] == 0.0

    def test_kappa_threshold_detection(self):
        """Drift detected when kappa < threshold."""
        # Create grades where patterns and judge systematically disagree
        grades = [
            _make_grade(f"XRAY-{i:03d}", pattern_pass=True, judge_fail_class="A") for i in range(10)
        ]
        report = compute_calibration_drift(grades, kappa_threshold=0.60)
        assert report.drift_detected is True

    def test_agreement_threshold_detection(self):
        """Drift detected when agreement < threshold."""
        grades = [
            _make_grade("XRAY-001", pattern_pass=True, judge_fail_class=None),
            _make_grade("XRAY-002", pattern_pass=True, judge_fail_class="A"),
            _make_grade("XRAY-003", pattern_pass=True, judge_fail_class="B"),
        ]
        # 1/3 agreement = 33.3% < 70%
        report = compute_calibration_drift(grades, agreement_threshold=0.70)
        assert report.drift_detected is True

    def test_grades_without_judge(self):
        """Grades missing judge_result are skipped."""
        grades = [
            {
                "task_id": "XRAY-001",
                "model": "m1",
                "passed": True,
                "pattern_result": {"all_required_pass": True},
                "judge_result": {},  # empty
            }
        ]
        report = compute_calibration_drift(grades)
        # No valid pairs to compare
        assert report.layer0_vs_layer2_agreement == 0.0


class TestCompareToHuman:
    """Test comparison to physician reference grades."""

    def test_no_human_grades(self, tmp_path):
        """Gracefully handles missing human grades."""
        path = tmp_path / "nonexistent.jsonl"
        result = compare_to_human(path, [])
        assert result is None

    def test_empty_human_grades(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        result = compare_to_human(path, [])
        assert result is None

    def test_valid_comparison(self, tmp_path):
        human_path = tmp_path / "human.jsonl"
        with open(human_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "task_id": "XRAY-001",
                        "dimension_scores": {"diagnostic_accuracy": 0.9, "finding_detection": 0.8},
                        "failure_class": None,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "task_id": "XRAY-002",
                        "dimension_scores": {"diagnostic_accuracy": 0.3, "finding_detection": 0.2},
                        "failure_class": "A",
                    }
                )
                + "\n"
            )

        judge_grades = [
            {
                "task_id": "XRAY-001",
                "dimension_scores": {"diagnostic_accuracy": 0.85, "finding_detection": 0.75},
                "failure_class": None,
            },
            {
                "task_id": "XRAY-002",
                "dimension_scores": {"diagnostic_accuracy": 0.4, "finding_detection": 0.3},
                "failure_class": "A",
            },
        ]

        result = compare_to_human(human_path, judge_grades)
        assert result is not None
        assert result.n_tasks == 2
        assert result.percent_agreement == 1.0  # Both agree on failure class


class TestFormatDriftReport:
    """Test markdown report formatting."""

    def test_no_drift(self):
        report = DriftReport(
            layer0_vs_layer2_agreement=0.85,
            layer0_vs_layer2_kappa=0.70,
            per_modality={},
            drift_detected=False,
            kappa_threshold=0.60,
            agreement_threshold=0.70,
            total_grades=100,
            human_comparison=None,
        )
        text = format_drift_report(report)
        assert "Calibration Drift" in text
        assert "No" in text
        assert "85.0%" in text

    def test_drift_detected(self):
        report = DriftReport(
            layer0_vs_layer2_agreement=0.50,
            layer0_vs_layer2_kappa=0.30,
            per_modality={"xray": {"agreement": 0.60, "kappa": 0.40}},
            drift_detected=True,
            kappa_threshold=0.60,
            agreement_threshold=0.70,
            total_grades=50,
            human_comparison=None,
        )
        text = format_drift_report(report)
        assert "YES" in text
        assert "xray" in text
