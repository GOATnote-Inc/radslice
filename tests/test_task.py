"""Tests for task.py — Task dataclass and YAML loader."""

from __future__ import annotations

import pytest

from radslice.task import (
    VALID_DIFFICULTIES,
    VALID_MODALITIES,
    VALID_TASK_TYPES,
    GroundTruth,
    KeyFinding,
    PatternCheck,
    Task,
    load_task,
    load_tasks_by_modality,
    load_tasks_from_dir,
    validate_task,
)

# --- Task frozen dataclass ---


class TestTask:
    def test_task_is_frozen(self, sample_task):
        with pytest.raises(AttributeError):
            sample_task.id = "changed"

    def test_task_fields(self, sample_task):
        assert sample_task.id == "XRAY-001"
        assert sample_task.modality == "xray"
        assert sample_task.anatomy == "chest"
        assert sample_task.task_type == "diagnosis"
        assert sample_task.difficulty == "intermediate"
        assert sample_task.condition_present is True
        assert sample_task.confusion_pair == "XRAY-043"

    def test_ground_truth_fields(self, sample_task):
        gt = sample_task.ground_truth
        assert gt.primary_diagnosis == "pneumothorax"
        assert "bullous emphysema" in gt.differential
        assert len(gt.key_findings) == 3
        assert gt.severity == "moderate"
        assert gt.laterality == "left"
        assert "tension pneumothorax" in gt.negatives

    def test_key_finding_frozen(self):
        kf = KeyFinding(finding="test", location="chest", required=True)
        with pytest.raises(AttributeError):
            kf.finding = "changed"

    def test_ground_truth_frozen(self):
        gt = GroundTruth(primary_diagnosis="test")
        with pytest.raises(AttributeError):
            gt.primary_diagnosis = "changed"


# --- PatternCheck ---


class TestPatternCheck:
    def test_regex_match(self):
        pc = PatternCheck(name="test", check_type="regex", pattern=r"\bpneumothorax\b")
        assert pc.check("Left pneumothorax identified") is True
        assert pc.check("Normal chest x-ray") is False

    def test_regex_case_insensitive(self):
        pc = PatternCheck(name="test", check_type="regex", pattern=r"\bPTX\b")
        assert pc.check("Small ptx noted") is True

    def test_contains(self):
        pc = PatternCheck(name="test", check_type="contains", pattern="pneumonia")
        assert pc.check("Right lower lobe pneumonia") is True
        assert pc.check("Normal lungs") is False

    def test_contains_case_insensitive(self):
        pc = PatternCheck(name="test", check_type="contains", pattern="PNEUMONIA")
        assert pc.check("bilateral pneumonia") is True

    def test_not_contains(self):
        pc = PatternCheck(name="test", check_type="not_contains", pattern="tension pneumothorax")
        assert pc.check("Simple pneumothorax") is True
        assert pc.check("Tension pneumothorax identified") is False

    def test_unknown_check_type(self):
        pc = PatternCheck(name="test", check_type="unknown", pattern="test")
        with pytest.raises(ValueError, match="Unknown check_type"):
            pc.check("test text")


# --- run_pattern_checks ---


class TestRunPatternChecks:
    def test_all_pass(self, sample_task, good_response):
        results = sample_task.run_pattern_checks(good_response)
        assert results["identifies_pneumothorax"] is True
        assert results["identifies_laterality"] is True
        assert results["no_tension_overcall"] is True

    def test_some_fail(self, sample_task, bad_response):
        results = sample_task.run_pattern_checks(bad_response)
        # "pneumothorax" regex matches even in negation context "No...pneumothorax"
        assert results["identifies_pneumothorax"] is True  # Regex limitation
        assert results["identifies_laterality"] is False  # "left" not mentioned

    def test_required_pass(self, sample_task, good_response):
        assert sample_task.required_pattern_checks_pass(good_response) is True

    def test_required_fail(self, sample_task, bad_response):
        assert sample_task.required_pattern_checks_pass(bad_response) is False


# --- validate_task ---


class TestValidation:
    def test_valid_task(self, sample_task):
        errors = validate_task(sample_task)
        assert errors == []

    def test_invalid_modality(self):
        task = Task(
            id="TEST-001",
            name="test",
            modality="invalid",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        errors = validate_task(task)
        assert any("modality" in e for e in errors)

    def test_invalid_task_type(self):
        task = Task(
            id="TEST-001",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="invalid",
            difficulty="basic",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        errors = validate_task(task)
        assert any("task_type" in e for e in errors)

    def test_invalid_difficulty(self):
        task = Task(
            id="TEST-001",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="impossible",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        errors = validate_task(task)
        assert any("difficulty" in e for e in errors)

    def test_empty_id(self):
        task = Task(
            id="",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        errors = validate_task(task)
        assert any("id" in e for e in errors)

    def test_empty_image_ref(self):
        task = Task(
            id="TEST-001",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        errors = validate_task(task)
        assert any("image_ref" in e for e in errors)

    def test_empty_diagnosis(self):
        task = Task(
            id="TEST-001",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="test.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis=""),
        )
        errors = validate_task(task)
        assert any("primary_diagnosis" in e for e in errors)


# --- YAML loading ---


class TestLoadTask:
    def test_load_from_yaml(self, sample_task_yaml):
        task = load_task(sample_task_yaml)
        assert task.id == "XRAY-TEST"
        assert task.modality == "xray"
        assert task.ground_truth.primary_diagnosis == "pneumonia"
        assert len(task.pattern_checks) == 2

    def test_load_invalid_yaml_raises(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("id: BAD\nmodality: invalid\n")
        with pytest.raises(Exception):
            load_task(bad_yaml)

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_task(tmp_path / "nonexistent.yaml")


class TestLoadTasksFromDir:
    def test_loads_all(self, sample_tasks_dir):
        tasks = load_tasks_from_dir(sample_tasks_dir)
        assert len(tasks) == 5

    def test_sorted_by_id(self, sample_tasks_dir):
        tasks = load_tasks_from_dir(sample_tasks_dir)
        ids = [t.id for t in tasks]
        assert ids == sorted(ids)

    def test_empty_dir(self, tmp_path):
        tasks = load_tasks_from_dir(tmp_path)
        assert tasks == []


class TestLoadTasksByModality:
    def test_groups_by_modality(self, sample_tasks_dir):
        grouped = load_tasks_by_modality(sample_tasks_dir)
        assert "xray" in grouped
        assert len(grouped["xray"]) == 5

    def test_filter_modality(self, sample_tasks_dir):
        grouped = load_tasks_by_modality(sample_tasks_dir, modality="ct")
        assert "ct" not in grouped  # No CT tasks in fixture

    def test_filter_existing_modality(self, sample_tasks_dir):
        grouped = load_tasks_by_modality(sample_tasks_dir, modality="xray")
        assert "xray" in grouped


# --- Constants ---


class TestConstants:
    def test_valid_modalities(self):
        assert "xray" in VALID_MODALITIES
        assert "ct" in VALID_MODALITIES
        assert "mri" in VALID_MODALITIES
        assert "ultrasound" in VALID_MODALITIES

    def test_valid_task_types(self):
        assert "diagnosis" in VALID_TASK_TYPES
        assert "vqa" in VALID_TASK_TYPES
        assert "finding_detection" in VALID_TASK_TYPES
        assert "report_generation" in VALID_TASK_TYPES

    def test_valid_difficulties(self):
        assert "basic" in VALID_DIFFICULTIES
        assert "expert" in VALID_DIFFICULTIES
