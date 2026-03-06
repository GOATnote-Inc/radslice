"""Tests for condition_id validation against OpenEM condition map."""

import pytest

from radslice.task import validate_condition_id, validate_task

# Minimal mock OpenEM condition map
MOCK_OPENEM_MAP = {
    "spontaneous-pneumothorax": ["pneumothorax"],
    "tension-headache": ["headache"],
    "stemi": ["myocardial-infarction"],
}


class TestValidateConditionId:
    def test_valid_condition_id(self):
        assert validate_condition_id("stemi", MOCK_OPENEM_MAP) is None

    def test_invalid_condition_id(self):
        err = validate_condition_id("nonexistent-condition", MOCK_OPENEM_MAP)
        assert err is not None
        assert "nonexistent-condition" in err
        assert "not found" in err

    def test_none_map_skips_validation(self):
        assert validate_condition_id("anything", None) is None

    def test_empty_map_rejects(self):
        err = validate_condition_id("stemi", {})
        assert err is not None


class TestValidateTaskWithOpenEM:
    @pytest.fixture
    def minimal_task(self):
        from radslice.task import GroundTruth, Task

        return Task(
            id="RS-001",
            name="Test task",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="pneumothorax"),
            condition_id="spontaneous-pneumothorax",
        )

    def test_valid_condition_no_errors(self, minimal_task):
        errors = validate_task(minimal_task, MOCK_OPENEM_MAP)
        assert not errors

    def test_invalid_condition_reports_error(self, minimal_task):
        from dataclasses import replace

        bad_task = replace(minimal_task, condition_id="fake-condition")
        errors = validate_task(bad_task, MOCK_OPENEM_MAP)
        assert any("fake-condition" in e for e in errors)

    def test_no_map_skips_openem_validation(self, minimal_task):
        from dataclasses import replace

        bad_task = replace(minimal_task, condition_id="fake-condition")
        errors = validate_task(bad_task, None)
        assert not any("not found in OpenEM" in e for e in errors)
