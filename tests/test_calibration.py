"""Tests for calibration.py — Cohen's kappa and calibration comparison."""

from __future__ import annotations

import json

import pytest

from radslice.grading.calibration import (
    CalibrationEntry,
    cohens_kappa,
    compute_calibration,
    load_calibration,
)


class TestCohensKappa:
    def test_perfect_agreement(self):
        labels = ["A", "B", "C", "A", "B"]
        k = cohens_kappa(labels, labels)
        assert k == pytest.approx(1.0)

    def test_no_agreement(self):
        a = ["A", "B", "A", "B"]
        b = ["B", "A", "B", "A"]
        k = cohens_kappa(a, b)
        assert k < 0

    def test_partial_agreement(self):
        a = ["A", "B", "C", "A", "B"]
        b = ["A", "B", "C", "B", "A"]
        k = cohens_kappa(a, b)
        assert 0 < k < 1

    def test_empty(self):
        assert cohens_kappa([], []) == 0.0

    def test_different_lengths_raises(self):
        with pytest.raises(ValueError):
            cohens_kappa(["A"], ["A", "B"])

    def test_binary(self):
        a = ["PASS", "FAIL", "PASS", "PASS", "FAIL"]
        b = ["PASS", "FAIL", "FAIL", "PASS", "FAIL"]
        k = cohens_kappa(a, b)
        assert -1 <= k <= 1


class TestCalibrationEntry:
    def test_frozen(self):
        entry = CalibrationEntry(
            task_id="T",
            dimension_scores={"diagnostic_accuracy": 0.9},
            failure_class=None,
        )
        with pytest.raises(AttributeError):
            entry.task_id = "changed"


class TestLoadCalibration:
    def test_load(self, tmp_path):
        path = tmp_path / "cal.jsonl"
        entries = [
            {
                "task_id": "XRAY-001",
                "dimension_scores": {"diagnostic_accuracy": 0.9},
                "failure_class": None,
            },
            {
                "task_id": "XRAY-002",
                "dimension_scores": {"diagnostic_accuracy": 0.3},
                "failure_class": "A",
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        loaded = load_calibration(path)
        assert len(loaded) == 2
        assert loaded[0].task_id == "XRAY-001"
        assert loaded[1].failure_class == "A"


class TestComputeCalibration:
    def test_perfect_calibration(self):
        human = [
            CalibrationEntry("T1", {"diagnostic_accuracy": 0.9}, None),
            CalibrationEntry("T2", {"diagnostic_accuracy": 0.3}, "A"),
        ]
        judge = [
            CalibrationEntry("T1", {"diagnostic_accuracy": 0.9}, None),
            CalibrationEntry("T2", {"diagnostic_accuracy": 0.3}, "A"),
        ]
        result = compute_calibration(human, judge)
        assert result.cohens_kappa == pytest.approx(1.0)
        assert result.percent_agreement == 1.0
        assert result.n_tasks == 2

    def test_no_overlap(self):
        human = [CalibrationEntry("T1", {}, None)]
        judge = [CalibrationEntry("T2", {}, None)]
        result = compute_calibration(human, judge)
        assert result.n_tasks == 0

    def test_partial_overlap(self):
        human = [
            CalibrationEntry("T1", {"diagnostic_accuracy": 0.9}, None),
            CalibrationEntry("T2", {"diagnostic_accuracy": 0.5}, "B"),
        ]
        judge = [
            CalibrationEntry("T1", {"diagnostic_accuracy": 0.8}, None),
            CalibrationEntry("T3", {"diagnostic_accuracy": 0.5}, "A"),
        ]
        result = compute_calibration(human, judge)
        assert result.n_tasks == 1

    def test_confusion_matrix(self):
        human = [
            CalibrationEntry("T1", {}, None),
            CalibrationEntry("T2", {}, "A"),
            CalibrationEntry("T3", {}, "A"),
        ]
        judge = [
            CalibrationEntry("T1", {}, None),
            CalibrationEntry("T2", {}, "A"),
            CalibrationEntry("T3", {}, None),
        ]
        result = compute_calibration(human, judge)
        assert result.confusion_matrix["A"]["PASS"] == 1
        assert result.confusion_matrix["A"]["A"] == 1
        assert result.confusion_matrix["PASS"]["PASS"] == 1
