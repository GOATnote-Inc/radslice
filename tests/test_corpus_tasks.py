"""Tests that validate all checked-in task YAMLs are well-formed."""

from __future__ import annotations

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
        from collections import Counter

        counts = Counter(t.modality for t in tasks)
        assert counts["xray"] >= 20
        assert counts["ct"] >= 10
        assert counts["mri"] >= 10
        assert counts["ultrasound"] >= 5

    def test_difficulty_distribution(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        difficulties = {t.difficulty for t in tasks}
        assert len(difficulties) >= 3, "Expected at least 3 difficulty levels"

    def test_confusion_pairs_valid(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        all_ids = {t.id for t in tasks}
        for task in tasks:
            if task.confusion_pair:
                assert task.confusion_pair in all_ids, (
                    f"{task.id} references unknown confusion_pair {task.confusion_pair}"
                )

    def test_task_type_distribution(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        task_types = {t.task_type for t in tasks}
        assert "diagnosis" in task_types
        assert len(task_types) >= 2, "Expected at least 2 task types"

    def test_normal_cases_exist(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        normal = [t for t in tasks if not t.condition_present]
        assert len(normal) > 0, "Expected at least one normal/negative case"

    def test_confusion_pairs_exist(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        pairs = [t for t in tasks if t.confusion_pair]
        assert len(pairs) > 0, "Expected at least one confusion pair"

    def test_reference_solutions_present(self):
        tasks = load_tasks_from_dir(TASKS_DIR)
        for task in tasks:
            assert task.reference_solution, f"{task.id} missing reference_solution"
