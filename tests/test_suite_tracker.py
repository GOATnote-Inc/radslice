"""Tests for suite membership tracking."""

import yaml

from radslice.analysis.suite_tracker import (
    SuiteMembership,
    TaskMembership,
    apply_promotion,
    apply_retirement,
    load_suite_membership,
    propose_promotions,
    propose_retirements,
    save_suite_membership,
    update_tracking,
)


class TestLoadSave:
    """Test YAML round-trip for suite membership."""

    def test_load_nonexistent(self, tmp_path):
        membership = load_suite_membership(tmp_path / "missing.yaml")
        assert isinstance(membership, SuiteMembership)
        assert membership.tasks == {}

    def test_round_trip(self, tmp_path):
        path = tmp_path / "suite.yaml"
        original = SuiteMembership()
        original.tasks["XRAY-001"] = TaskMembership(
            suite="capability",
            consecutive_all_pass=3,
            consecutive_any_fail=0,
        )
        original.tasks["CT-001"] = TaskMembership(
            suite="regression",
            consecutive_all_pass=0,
            consecutive_any_fail=2,
            promoted_date="2026-02-28T00:00:00+00:00",
        )

        save_suite_membership(original, path)
        loaded = load_suite_membership(path)

        assert "XRAY-001" in loaded.tasks
        assert loaded.tasks["XRAY-001"].suite == "capability"
        assert loaded.tasks["XRAY-001"].consecutive_all_pass == 3
        assert "CT-001" in loaded.tasks
        assert loaded.tasks["CT-001"].suite == "regression"
        assert loaded.tasks["CT-001"].promoted_date is not None

    def test_round_trip_yaml_readable(self, tmp_path):
        """Saved YAML is human-readable."""
        path = tmp_path / "suite.yaml"
        original = SuiteMembership()
        original.tasks["XRAY-001"] = TaskMembership(suite="capability")
        save_suite_membership(original, path)

        with open(path) as f:
            data = yaml.safe_load(f)
        assert "tasks" in data
        assert "XRAY-001" in data["tasks"]

    def test_load_empty_yaml(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        membership = load_suite_membership(path)
        assert isinstance(membership, SuiteMembership)


class TestUpdateTracking:
    """Test consecutive pass/fail counter updates."""

    def test_all_pass_increments(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership()

        grades = [
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 1},
        ]
        update_tracking(membership, grades)
        assert membership.tasks["XRAY-001"].consecutive_all_pass == 1
        assert membership.tasks["XRAY-001"].consecutive_any_fail == 0

    def test_any_fail_resets_pass_counter(self):
        membership = SuiteMembership()
        membership.tasks["CT-001"] = TaskMembership(consecutive_all_pass=5)

        grades = [
            {"task_id": "CT-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            {"task_id": "CT-001", "model": "gpt-5.2", "passed": False, "trial": 1},
        ]
        update_tracking(membership, grades)
        assert membership.tasks["CT-001"].consecutive_all_pass == 0
        assert membership.tasks["CT-001"].consecutive_any_fail == 1

    def test_new_task_auto_created(self):
        membership = SuiteMembership()
        grades = [
            {"task_id": "MRI-001", "model": "gpt-5.2", "passed": True, "trial": 0},
        ]
        update_tracking(membership, grades)
        assert "MRI-001" in membership.tasks
        assert membership.tasks["MRI-001"].suite == "capability"

    def test_multiple_tasks_updated(self):
        membership = SuiteMembership()
        grades = [
            {"task_id": "XRAY-001", "model": "m1", "passed": True, "trial": 0},
            {"task_id": "CT-001", "model": "m1", "passed": False, "trial": 0},
        ]
        update_tracking(membership, grades)
        assert membership.tasks["XRAY-001"].consecutive_all_pass == 1
        assert membership.tasks["CT-001"].consecutive_any_fail == 1


class TestProposals:
    """Test promotion and retirement proposal logic."""

    def test_propose_promotions_discriminating(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership()

        grades = [
            # Model A passes
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 1},
            # Model B fails
            {"task_id": "XRAY-001", "model": "opus-4-6", "passed": False, "trial": 0},
            {"task_id": "XRAY-001", "model": "opus-4-6", "passed": False, "trial": 1},
            # Model C fails
            {"task_id": "XRAY-001", "model": "gemini", "passed": False, "trial": 0},
            {"task_id": "XRAY-001", "model": "gemini", "passed": False, "trial": 1},
        ]
        proposals = propose_promotions(grades, membership, min_models_broken=2)
        assert "XRAY-001" in proposals

    def test_propose_promotions_not_enough_failing(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership()

        grades = [
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            {"task_id": "XRAY-001", "model": "opus-4-6", "passed": False, "trial": 0},
        ]
        # Need min_models_broken=2, only 1 failing
        proposals = propose_promotions(grades, membership, min_models_broken=2)
        assert "XRAY-001" not in proposals

    def test_skip_already_in_regression(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership(suite="regression")

        grades = [
            {"task_id": "XRAY-001", "model": "gpt-5.2", "passed": True, "trial": 0},
            {"task_id": "XRAY-001", "model": "opus-4-6", "passed": False, "trial": 0},
            {"task_id": "XRAY-001", "model": "gemini", "passed": False, "trial": 0},
        ]
        proposals = propose_promotions(grades, membership, min_models_broken=2)
        assert "XRAY-001" not in proposals

    def test_propose_retirements(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership(suite="capability", consecutive_all_pass=5)
        membership.tasks["XRAY-002"] = TaskMembership(suite="capability", consecutive_all_pass=2)

        proposals = propose_retirements(membership, max_consecutive_passes=5)
        assert "XRAY-001" in proposals
        assert "XRAY-002" not in proposals

    def test_propose_retirements_ignores_regression(self):
        membership = SuiteMembership()
        membership.tasks["CT-001"] = TaskMembership(suite="regression", consecutive_all_pass=10)
        proposals = propose_retirements(membership, max_consecutive_passes=5)
        assert "CT-001" not in proposals


class TestApplyChanges:
    """Test promotion and retirement application."""

    def test_apply_promotion(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership(suite="capability")
        apply_promotion(membership, "XRAY-001")
        assert membership.tasks["XRAY-001"].suite == "regression"
        assert membership.tasks["XRAY-001"].promoted_date is not None

    def test_apply_retirement(self):
        membership = SuiteMembership()
        membership.tasks["CT-001"] = TaskMembership(suite="capability")
        apply_retirement(membership, "CT-001")
        assert membership.tasks["CT-001"].suite == "retired"
        assert membership.tasks["CT-001"].retired_date is not None

    def test_apply_promotion_new_task(self):
        """Promoting a task not yet tracked creates the entry."""
        membership = SuiteMembership()
        apply_promotion(membership, "MRI-001")
        assert "MRI-001" in membership.tasks
        assert membership.tasks["MRI-001"].suite == "regression"

    def test_recount_after_promotion(self):
        membership = SuiteMembership()
        membership.tasks["XRAY-001"] = TaskMembership(suite="capability")
        membership.tasks["XRAY-002"] = TaskMembership(suite="capability")
        apply_promotion(membership, "XRAY-001")
        assert membership.regression["xray"] == 1
        assert membership.capability["xray"] == 1
