"""Tests for saturation detection module."""

import json
from pathlib import Path

from radslice.analysis.saturation import (
    CorpusSaturationReport,
    detect_saturation,
    format_saturation_report,
)


def _write_grades(tmpdir: Path, run_name: str, grades: list[dict]) -> Path:
    """Write grade dicts to a grades.jsonl in a temp results dir."""
    run_dir = tmpdir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    grades_path = run_dir / "grades.jsonl"
    with open(grades_path, "w") as f:
        for g in grades:
            f.write(json.dumps(g) + "\n")
    return run_dir


class TestDetectSaturation:
    """Test saturation detection logic."""

    def test_empty_results(self):
        report = detect_saturation([])
        assert report.total_tasks == 0
        assert report.saturated_tasks == 0
        assert report.saturation_rate == 0.0
        assert report.needs_evolution == []

    def test_all_pass_single_run(self, tmp_path):
        """Single run cannot trigger saturation (min_consecutive_runs=3)."""
        grades = [
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": i}
            for i in range(5)
        ]
        run_dir = _write_grades(tmp_path, "run1", grades)
        report = detect_saturation([run_dir])
        assert report.total_tasks == 1
        assert report.saturated_tasks == 0

    def test_all_pass_three_runs_saturated(self, tmp_path):
        """Three consecutive all-pass runs triggers saturation."""
        runs = []
        for run_idx in range(3):
            grades = [
                {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": i}
                for i in range(3)
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        report = detect_saturation(runs, threshold=0.95, min_consecutive_runs=3)
        assert report.total_tasks == 1
        assert report.saturated_tasks == 1
        assert report.saturation_rate == 1.0
        assert "XRAY-001" in report.needs_evolution

    def test_mixed_results_not_saturated(self, tmp_path):
        """Tasks with failures are not saturated."""
        runs = []
        for run_idx in range(3):
            grades = [
                {"task_id": "CT-001", "model": "gpt-5.2", "passed": True, "trial": 0},
                {"task_id": "CT-001", "model": "gpt-5.2", "passed": False, "trial": 1},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        report = detect_saturation(runs, threshold=0.95, min_consecutive_runs=3)
        assert report.saturated_tasks == 0

    def test_multi_model_all_must_saturate(self, tmp_path):
        """All models must be saturated for a task to be saturated."""
        runs = []
        for run_idx in range(3):
            grades = [
                # Model A always passes
                {"task_id": "MRI-001", "model": "gpt-5.2", "passed": True, "trial": 0},
                {"task_id": "MRI-001", "model": "gpt-5.2", "passed": True, "trial": 1},
                # Model B sometimes fails
                {"task_id": "MRI-001", "model": "opus-4-6", "passed": True, "trial": 0},
                {"task_id": "MRI-001", "model": "opus-4-6", "passed": False, "trial": 1},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        report = detect_saturation(runs, threshold=0.95, min_consecutive_runs=3)
        assert report.saturated_tasks == 0

    def test_multi_model_both_saturated(self, tmp_path):
        """Both models passing for 3 runs triggers saturation."""
        runs = []
        for run_idx in range(3):
            grades = [
                {"task_id": "XRAY-010", "model": "gpt-5.2", "passed": True, "trial": 0},
                {"task_id": "XRAY-010", "model": "gpt-5.2", "passed": True, "trial": 1},
                {"task_id": "XRAY-010", "model": "opus-4-6", "passed": True, "trial": 0},
                {"task_id": "XRAY-010", "model": "opus-4-6", "passed": True, "trial": 1},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        report = detect_saturation(runs, threshold=0.95, min_consecutive_runs=3)
        assert report.saturated_tasks == 1
        assert "XRAY-010" in report.needs_evolution

    def test_per_modality_breakdown(self, tmp_path):
        """Per-modality counts are correct."""
        runs = []
        for run_idx in range(3):
            grades = [
                {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
                {"task_id": "CT-001", "model": "gpt-5.2", "passed": True, "trial": 0},
                {"task_id": "CT-001", "model": "gpt-5.2", "passed": False, "trial": 1},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        report = detect_saturation(runs, threshold=0.95, min_consecutive_runs=3)
        assert "xray" in report.per_modality
        assert "ct" in report.per_modality
        assert report.per_modality["xray"]["total"] == 1
        assert report.per_modality["ct"]["total"] == 1

    def test_boundary_threshold(self, tmp_path):
        """Task at exactly threshold is still saturated."""
        runs = []
        for run_idx in range(3):
            grades = [
                {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        # threshold=1.0, rate=1.0 — should saturate
        report = detect_saturation(runs, threshold=1.0, min_consecutive_runs=3)
        assert report.saturated_tasks == 1

    def test_missing_grades_file(self, tmp_path):
        """Gracefully handle missing grades.jsonl."""
        empty_dir = tmp_path / "empty_run"
        empty_dir.mkdir()
        report = detect_saturation([empty_dir])
        assert report.total_tasks == 0

    def test_custom_min_consecutive(self, tmp_path):
        """Custom min_consecutive_runs threshold."""
        runs = []
        for run_idx in range(5):
            grades = [
                {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            ]
            run_dir = _write_grades(tmp_path, f"run{run_idx}", grades)
            runs.append(run_dir)

        # Only 3 runs, but min=5
        report_3 = detect_saturation(runs[:3], threshold=0.95, min_consecutive_runs=5)
        assert report_3.saturated_tasks == 0

        # 5 runs, min=5
        report_5 = detect_saturation(runs, threshold=0.95, min_consecutive_runs=5)
        assert report_5.saturated_tasks == 1


class TestFormatSaturationReport:
    """Test markdown report formatting."""

    def test_empty_report(self):
        report = CorpusSaturationReport(
            total_tasks=0,
            saturated_tasks=0,
            saturation_rate=0.0,
            per_modality={},
            per_difficulty={},
            task_details=[],
            needs_evolution=[],
            threshold=0.95,
            min_consecutive_runs=3,
        )
        text = format_saturation_report(report)
        assert "Saturation Report" in text
        assert "0" in text

    def test_report_with_data(self):
        report = CorpusSaturationReport(
            total_tasks=10,
            saturated_tasks=2,
            saturation_rate=0.2,
            per_modality={"xray": {"total": 5, "saturated": 1}},
            per_difficulty={},
            task_details=[],
            needs_evolution=["XRAY-001", "CT-005"],
            threshold=0.95,
            min_consecutive_runs=3,
        )
        text = format_saturation_report(report)
        assert "20.0%" in text
        assert "XRAY-001" in text
        assert "CT-005" in text
        assert "xray" in text
