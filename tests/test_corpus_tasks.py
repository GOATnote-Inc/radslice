"""Tests that validate all checked-in task YAMLs are well-formed."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from radslice.task import (
    load_task,
    load_tasks_from_dir,
    validate_task,
)

TASKS_DIR = Path("configs/tasks")


def _all_task_yamls():
    """Collect all task YAML paths."""
    if not TASKS_DIR.exists():
        return []
    return sorted(TASKS_DIR.rglob("*.yaml"))


@pytest.mark.skipif(not TASKS_DIR.exists(), reason="Task YAMLs not available")
class TestCorpusTasks:
    """Validate every checked-in task YAML."""

    def test_all_tasks_load(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        assert len(tasks) > 0, "Expected at least one task YAML"

    @pytest.mark.parametrize("yaml_path", _all_task_yamls(), ids=lambda p: p.stem)
    def test_task_validates(self, yaml_path):
        task = load_task(yaml_path)
        errors = validate_task(task)
        assert errors == [], f"{yaml_path.stem}: {errors}"

    @pytest.mark.parametrize("yaml_path", _all_task_yamls(), ids=lambda p: p.stem)
    def test_task_has_pattern_checks(self, yaml_path):
        task = load_task(yaml_path)
        assert len(task.pattern_checks) > 0, f"{task.id} has no pattern checks"

    @pytest.mark.parametrize("yaml_path", _all_task_yamls(), ids=lambda p: p.stem)
    def test_task_has_ground_truth(self, yaml_path):
        task = load_task(yaml_path)
        assert task.ground_truth.primary_diagnosis, f"{task.id} missing diagnosis"

    def test_unique_task_ids(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        ids = [t.id for t in tasks]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_modality_distribution(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        modalities = {t.modality for t in tasks}
        for m in ("xray", "ct", "mri", "ultrasound"):
            assert m in modalities, f"Missing modality: {m}"

    def test_modality_counts(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        counts = Counter(t.modality for t in tasks)
        assert counts["xray"] >= 50
        assert counts["ct"] >= 80
        assert counts["mri"] >= 40
        assert counts["ultrasound"] >= 60

    def test_difficulty_distribution(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        difficulties = {t.difficulty for t in tasks}
        assert len(difficulties) >= 3, "Expected at least 3 difficulty levels"

    def test_condition_id_present(self):
        """Every task must link to an OpenEM condition."""
        tasks = load_tasks_from_dir(TASKS_DIR)
        for task in tasks:
            assert task.condition_id, f"{task.id} missing condition_id"

    def test_condition_id_format(self):
        """condition_id should be kebab-case."""
        tasks = load_tasks_from_dir(TASKS_DIR)
        import re

        for task in tasks:
            if task.condition_id:
                assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", task.condition_id), (
                    f"{task.id} has invalid condition_id format: {task.condition_id}"
                )

    def test_condition_coverage(self):
        """Should cover a substantial number of unique OpenEM conditions."""
        tasks = load_tasks_from_dir(TASKS_DIR)
        conditions = {t.condition_id for t in tasks}
        assert len(conditions) >= 100, f"Only {len(conditions)} unique conditions, expected >= 100"

    def test_lostbench_scenario_format(self):
        """lostbench_scenario_id should be MTR-NNN or DEF-NNN format when present."""
        tasks = load_tasks_from_dir(TASKS_DIR)
        import re

        for task in tasks:
            if task.lostbench_scenario_id:
                assert re.match(r"^(MTR|DEF)-\d{3}$", task.lostbench_scenario_id), (
                    f"{task.id} has invalid lostbench_scenario_id: {task.lostbench_scenario_id}"
                )

    def test_reference_solutions_present(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        for task in tasks:
            assert task.reference_solution, f"{task.id} missing reference_solution"
