"""Tests for analysis modules — per_modality, per_anatomy, regression, report."""

from __future__ import annotations

import json

from radslice.analysis.per_anatomy import anatomy_breakdown
from radslice.analysis.per_modality import modality_breakdown
from radslice.analysis.regression import detect_regression
from radslice.analysis.report import format_report


class TestModalityBreakdown:
    def test_basic_breakdown(self, sample_grades):
        result = modality_breakdown(sample_grades)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_pass_rate(self, sample_grades):
        result = modality_breakdown(sample_grades)
        for mod, info in result.items():
            assert 0.0 <= info["pass_rate"] <= 1.0
            assert info["total_grades"] > 0

    def test_wilson_ci_present(self, sample_grades):
        result = modality_breakdown(sample_grades)
        for mod, info in result.items():
            wci = info["wilson_ci"]
            assert len(wci) == 2
            assert 0.0 <= wci[0] <= wci[1] <= 1.0

    def test_failure_classes(self, sample_grades):
        result = modality_breakdown(sample_grades)
        for mod, info in result.items():
            fc = info["failure_classes"]
            assert isinstance(fc, dict)

    def test_empty_grades(self):
        result = modality_breakdown([])
        assert result == {}

    def test_mean_score(self, sample_grades):
        result = modality_breakdown(sample_grades)
        for mod, info in result.items():
            assert 0.0 <= info["mean_score"] <= 1.0


class TestAnatomyBreakdown:
    def test_basic_breakdown(self, sample_grades):
        result = anatomy_breakdown(sample_grades)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_pass_rate(self, sample_grades):
        result = anatomy_breakdown(sample_grades)
        for anat, info in result.items():
            assert 0.0 <= info["pass_rate"] <= 1.0

    def test_dimension_means(self, sample_grades):
        result = anatomy_breakdown(sample_grades)
        for anat, info in result.items():
            for dim, mean in info["dimension_means"].items():
                assert 0.0 <= mean <= 1.0

    def test_empty_grades(self):
        result = anatomy_breakdown([])
        assert result == {}


class TestRegression:
    def test_no_regression(self):
        current = [
            {"task_id": "XRAY-001", "passed": True, "metadata": {"modality": "xray"}},
            {"task_id": "XRAY-002", "passed": True, "metadata": {"modality": "xray"}},
        ]
        prior = [
            {"task_id": "XRAY-001", "passed": True, "metadata": {"modality": "xray"}},
            {"task_id": "XRAY-002", "passed": True, "metadata": {"modality": "xray"}},
        ]
        result = detect_regression(current, prior)
        assert result["overall_regression"] is False
        assert result["regressed_modalities"] == []

    def test_regression_detected(self):
        current = [
            {"task_id": f"XRAY-{i:03d}", "passed": False, "metadata": {"modality": "xray"}}
            for i in range(50)
        ]
        prior = [
            {"task_id": f"XRAY-{i:03d}", "passed": True, "metadata": {"modality": "xray"}}
            for i in range(50)
        ]
        result = detect_regression(current, prior)
        assert result["overall_regression"] is True
        assert "xray" in result["regressed_modalities"]

    def test_z_scores_present(self):
        current = [
            {"task_id": "CT-001", "passed": True, "metadata": {"modality": "ct"}},
            {"task_id": "CT-002", "passed": False, "metadata": {"modality": "ct"}},
        ]
        prior = [
            {"task_id": "CT-001", "passed": True, "metadata": {"modality": "ct"}},
            {"task_id": "CT-002", "passed": True, "metadata": {"modality": "ct"}},
        ]
        result = detect_regression(current, prior)
        assert "ct" in result["z_scores"]

    def test_empty_grades(self):
        result = detect_regression([], [])
        assert result["overall_regression"] is False


class TestFormatReport:
    def test_markdown_format(self, sample_grades):
        data = {
            "total_grades": len(sample_grades),
            "by_modality": modality_breakdown(sample_grades),
        }
        output = format_report(data, "markdown")
        assert "# RadSlice Evaluation Report" in output
        assert "Per-Modality Results" in output
        assert "pass@k" in output

    def test_json_format(self, sample_grades):
        data = {
            "total_grades": len(sample_grades),
            "by_modality": modality_breakdown(sample_grades),
        }
        output = format_report(data, "json")
        parsed = json.loads(output)
        assert "total_grades" in parsed
        assert "by_modality" in parsed

    def test_csv_format(self, sample_grades):
        data = {
            "by_modality": modality_breakdown(sample_grades),
        }
        output = format_report(data, "csv")
        assert "modality" in output
        assert "pass_rate" in output

    def test_comparison_report(self):
        data = {
            "run_a": "results/run_001",
            "total_grades": 10,
            "comparison": {
                "run_b": "results/run_002",
                "total_grades_b": 10,
                "regression": {
                    "overall_regression": False,
                    "regressed_modalities": [],
                    "details": {},
                },
            },
        }
        output = format_report(data, "markdown")
        assert "Regression Analysis" in output
        assert "No regression detected" in output

    def test_regression_report(self):
        data = {
            "run_a": "results/run_001",
            "total_grades": 10,
            "comparison": {
                "run_b": "results/run_002",
                "total_grades_b": 10,
                "regression": {
                    "overall_regression": True,
                    "regressed_modalities": ["xray"],
                    "details": {
                        "xray": {
                            "current": {"passed": 2, "total": 10},
                            "prior": {"passed": 8, "total": 10},
                            "z_score": -2.5,
                            "regression": True,
                        }
                    },
                },
            },
        }
        output = format_report(data, "markdown")
        assert "REGRESSION DETECTED" in output
        assert "xray" in output

    def test_anatomy_report(self, sample_grades):
        data = {
            "by_anatomy": anatomy_breakdown(sample_grades),
        }
        output = format_report(data, "markdown")
        assert "Per-Anatomy Results" in output
