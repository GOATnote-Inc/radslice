"""Tests for cross-repo correlation module."""

import json
from pathlib import Path

import yaml

from radslice.analysis.cross_repo import (
    CrossRepoFinding,
    build_condition_map,
    build_lostbench_map,
    correlate_findings,
    generate_cross_repo_report,
)


def _make_task_yaml(
    tasks_dir: Path, task_id: str, condition_id: str, modality: str = "xray", lostbench_id: str = ""
) -> Path:
    """Create a minimal task YAML."""
    mod_dir = tasks_dir / modality
    mod_dir.mkdir(parents=True, exist_ok=True)
    task = {
        "id": task_id,
        "name": f"Test {task_id}",
        "modality": modality,
        "condition_id": condition_id,
        "lostbench_scenario_id": lostbench_id,
        "anatomy": "chest",
        "task_type": "diagnosis",
        "difficulty": "intermediate",
        "image_ref": "test.png",
        "ground_truth": {"primary_diagnosis": "test"},
        "pattern_checks": [],
        "reference_solution": "test",
    }
    path = mod_dir / f"{task_id}.yaml"
    with open(path, "w") as f:
        yaml.dump(task, f)
    return path


def _write_grades(results_dir: Path, grades: list[dict]) -> None:
    """Write grades.jsonl."""
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "grades.jsonl", "w") as f:
        for g in grades:
            f.write(json.dumps(g) + "\n")


class TestBuildConditionMap:
    """Test condition_id -> task_ids mapping."""

    def test_basic_mapping(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "tension-pneumothorax")
        _make_task_yaml(tasks_dir, "CT-001", "tension-pneumothorax", "ct")
        _make_task_yaml(tasks_dir, "XRAY-002", "acute-heart-failure")

        cmap = build_condition_map(tasks_dir)
        assert "tension-pneumothorax" in cmap
        assert set(cmap["tension-pneumothorax"]) == {"XRAY-001", "CT-001"}
        assert cmap["acute-heart-failure"] == ["XRAY-002"]

    def test_empty_dir(self, tmp_path):
        tasks_dir = tmp_path / "empty"
        tasks_dir.mkdir()
        cmap = build_condition_map(tasks_dir)
        assert cmap == {}

    def test_invalid_yaml_skipped(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "bad.yaml").write_text("invalid: [yaml: {broken")
        cmap = build_condition_map(tasks_dir)
        assert cmap == {}


class TestBuildLostBenchMap:
    """Test condition_id -> lostbench_scenario_ids mapping."""

    def test_with_lostbench_ids(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "tension-pneumothorax", lostbench_id="MTR-042")
        _make_task_yaml(tasks_dir, "CT-001", "tension-pneumothorax", "ct", lostbench_id="MTR-042")
        _make_task_yaml(tasks_dir, "XRAY-002", "acute-heart-failure")

        lb_map = build_lostbench_map(tasks_dir)
        assert "tension-pneumothorax" in lb_map
        assert lb_map["tension-pneumothorax"] == ["MTR-042"]
        assert "acute-heart-failure" not in lb_map

    def test_empty_lostbench_id_excluded(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "test-cond", lostbench_id="")

        lb_map = build_lostbench_map(tasks_dir)
        assert lb_map == {}


class TestCorrelateFindings:
    """Test cross-repo correlation logic."""

    def test_both_pass(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a", lostbench_id="MTR-001")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": True},
            ],
        )

        lb_dir = tmp_path / "lb_results"
        lb_dir.mkdir()
        with open(lb_dir / "grades.jsonl", "w") as f:
            f.write(json.dumps({"scenario_id": "MTR-001", "passed": True}) + "\n")

        findings = correlate_findings(rs_dir, lb_dir, tasks_dir)
        assert len(findings) == 1
        assert findings[0].classification == "both_pass"

    def test_both_fail(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a", lostbench_id="MTR-001")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": False},
            ],
        )

        lb_dir = tmp_path / "lb_results"
        lb_dir.mkdir()
        with open(lb_dir / "grades.jsonl", "w") as f:
            f.write(json.dumps({"scenario_id": "MTR-001", "passed": False}) + "\n")

        findings = correlate_findings(rs_dir, lb_dir, tasks_dir)
        assert findings[0].classification == "both_fail"

    def test_radslice_only_fail(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a", lostbench_id="MTR-001")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": False},
            ],
        )

        lb_dir = tmp_path / "lb_results"
        lb_dir.mkdir()
        with open(lb_dir / "grades.jsonl", "w") as f:
            f.write(json.dumps({"scenario_id": "MTR-001", "passed": True}) + "\n")

        findings = correlate_findings(rs_dir, lb_dir, tasks_dir)
        assert findings[0].classification == "radslice_only_fail"

    def test_lostbench_only_fail(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a", lostbench_id="MTR-001")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": True},
            ],
        )

        lb_dir = tmp_path / "lb_results"
        lb_dir.mkdir()
        with open(lb_dir / "grades.jsonl", "w") as f:
            f.write(json.dumps({"scenario_id": "MTR-001", "passed": False}) + "\n")

        findings = correlate_findings(rs_dir, lb_dir, tasks_dir)
        assert findings[0].classification == "lostbench_only_fail"

    def test_no_lostbench_dir(self, tmp_path):
        """Graceful degradation without LostBench data."""
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": True},
            ],
        )

        findings = correlate_findings(rs_dir, None, tasks_dir)
        assert len(findings) == 1
        assert findings[0].lostbench_pass_rate is None

    def test_no_results(self, tmp_path):
        """Conditions with no results are skipped."""
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a")

        rs_dir = tmp_path / "rs_results"
        rs_dir.mkdir()
        (rs_dir / "grades.jsonl").write_text("")

        findings = correlate_findings(rs_dir, None, tasks_dir)
        assert len(findings) == 0

    def test_multiple_conditions(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        _make_task_yaml(tasks_dir, "XRAY-001", "cond-a")
        _make_task_yaml(tasks_dir, "XRAY-002", "cond-b")

        rs_dir = tmp_path / "rs_results"
        _write_grades(
            rs_dir,
            [
                {"task_id": "XRAY-001", "model": "m1", "passed": True},
                {"task_id": "XRAY-002", "model": "m1", "passed": False},
            ],
        )

        findings = correlate_findings(rs_dir, None, tasks_dir)
        assert len(findings) == 2


class TestGenerateReport:
    """Test markdown report generation."""

    def test_empty_findings(self):
        text = generate_cross_repo_report([])
        assert "Cross-Repo" in text
        assert "0" in text

    def test_report_with_divergence(self):
        findings = [
            CrossRepoFinding(
                condition_id="tension-pneumothorax",
                radslice_task_ids=["XRAY-042"],
                lostbench_scenario_ids=["MTR-042"],
                classification="radslice_only_fail",
                radslice_pass_rate=0.2,
                lostbench_pass_rate=0.8,
            ),
        ]
        text = generate_cross_repo_report(findings)
        assert "tension-pneumothorax" in text
        assert "radslice_only_fail" in text
        assert "Divergent" in text

    def test_report_with_both_fail(self):
        findings = [
            CrossRepoFinding(
                condition_id="testicular-torsion",
                radslice_task_ids=["US-010"],
                lostbench_scenario_ids=["MTR-005"],
                classification="both_fail",
                radslice_pass_rate=0.1,
                lostbench_pass_rate=0.2,
            ),
        ]
        text = generate_cross_repo_report(findings)
        assert "Both-Fail" in text
        assert "testicular-torsion" in text
