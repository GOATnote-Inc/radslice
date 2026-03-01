"""Tests for incidental_detection task type: loading, validation, scoring, prompts."""

from __future__ import annotations

import pytest
import yaml

from radslice.executor import PROMPT_TEMPLATES, _build_prompt
from radslice.grading.judge import (
    JUDGE_SYSTEM_PROMPT_INCIDENTAL,
    build_judge_prompt,
)
from radslice.grading.patterns import run_task_patterns
from radslice.task import (
    GroundTruth,
    IncidentalFinding,
    KeyFinding,
    PatternCheck,
    Task,
    TaskValidationError,
    load_task,
    validate_task,
)


class TestIncidentalTaskSchema:
    """Tests for incidental_detection dataclass and validation."""

    def test_incidental_finding_frozen(self):
        inc = IncidentalFinding(
            finding="hepatic steatosis",
            location="liver",
            clinical_significance="incidental",
            recommended_action="routine follow-up",
        )
        assert inc.finding == "hepatic steatosis"
        with pytest.raises(AttributeError):
            inc.finding = "changed"  # type: ignore[misc]

    def test_ground_truth_with_incidentals(self):
        gt = GroundTruth(
            primary_diagnosis="cholelithiasis",
            incidental_findings=[
                IncidentalFinding(
                    finding="hepatic steatosis",
                    location="liver",
                    clinical_significance="incidental",
                    recommended_action="routine follow-up",
                ),
            ],
        )
        assert len(gt.incidental_findings) == 1
        assert gt.incidental_findings[0].clinical_significance == "incidental"

    def test_valid_incidental_task(self, sample_incidental_task):
        errors = validate_task(sample_incidental_task)
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_incidental_task_requires_findings(self):
        task = Task(
            id="CT-INC-BAD",
            name="Bad incidental task",
            modality="ct",
            anatomy="abdomen",
            task_type="incidental_detection",
            difficulty="basic",
            image_ref="ct/test.png",
            prompt_template="incidental_detection",
            ground_truth=GroundTruth(
                primary_diagnosis="cholelithiasis",
                # No incidental_findings!
            ),
            condition_id="cholelithiasis",
        )
        errors = validate_task(task)
        assert any("incidental_findings" in e for e in errors)

    def test_incidental_task_type_valid(self):
        from radslice.task import VALID_TASK_TYPES

        assert "incidental_detection" in VALID_TASK_TYPES


class TestIncidentalTaskLoading:
    """Tests for loading incidental tasks from YAML."""

    def test_load_incidental_yaml(self, tmp_path):
        task_data = {
            "id": "CT-INC-LOAD",
            "name": "Load test incidental",
            "modality": "ct",
            "anatomy": "abdomen",
            "task_type": "incidental_detection",
            "difficulty": "advanced",
            "image_ref": "ct/test.png",
            "prompt_template": "incidental_detection",
            "ground_truth": {
                "primary_diagnosis": "cholelithiasis",
                "incidental_findings": [
                    {
                        "finding": "hepatic steatosis",
                        "location": "liver",
                        "clinical_significance": "incidental",
                        "recommended_action": "routine follow-up",
                    },
                    {
                        "finding": "renal cyst",
                        "location": "left kidney",
                        "clinical_significance": "benign",
                        "recommended_action": "no action",
                    },
                ],
            },
            "condition_id": "cholelithiasis",
        }
        path = tmp_path / "CT-INC-LOAD.yaml"
        with open(path, "w") as f:
            yaml.dump(task_data, f)

        task = load_task(path)
        assert task.task_type == "incidental_detection"
        assert len(task.ground_truth.incidental_findings) == 2
        assert task.ground_truth.incidental_findings[0].finding == "hepatic steatosis"
        assert task.ground_truth.incidental_findings[1].clinical_significance == "benign"


class TestIncidentalPatternScoring:
    """Tests for pattern check scoring with incidental tasks."""

    def test_patterns_detect_incidentals(self, sample_incidental_task):
        good_response = (
            "Abdominal CT demonstrates cholelithiasis with multiple gallstones "
            "in the gallbladder. Incidental findings include hepatic steatosis "
            "(fatty liver) diffusely involving the liver parenchyma, and a simple "
            "renal cyst in the right kidney."
        )
        result = run_task_patterns(sample_incidental_task, good_response)
        assert result.all_required_pass

    def test_patterns_miss_incidentals(self, sample_incidental_task):
        partial_response = (
            "Abdominal CT shows cholelithiasis. No other abnormalities identified."
        )
        result = run_task_patterns(sample_incidental_task, partial_response)
        # Should find cholelithiasis but miss steatosis
        assert result.checks.get("identifies_gallstones", False)
        assert not result.checks.get("identifies_steatosis", False)
        assert not result.all_required_pass


class TestIncidentalPromptBuilding:
    """Tests for prompt template and judge prompt construction."""

    def test_incidental_prompt_template_exists(self):
        assert "incidental_detection" in PROMPT_TEMPLATES

    def test_build_prompt_incidental(self, sample_incidental_task):
        prompt = _build_prompt(sample_incidental_task)
        assert "incidental" in prompt.lower()
        assert "clinical significance" in prompt.lower()

    def test_incidental_judge_system_prompt(self):
        assert "incidental" in JUDGE_SYSTEM_PROMPT_INCIDENTAL.lower()
        assert "finding_detection" in JUDGE_SYSTEM_PROMPT_INCIDENTAL
        assert "0.35" in JUDGE_SYSTEM_PROMPT_INCIDENTAL  # Higher weight for finding detection

    def test_judge_prompt_includes_incidentals(self):
        gt = {
            "primary_diagnosis": "cholelithiasis",
            "differential": [],
            "severity": "moderate",
            "laterality": "",
            "key_findings": [],
            "negatives": [],
            "incidental_findings": [
                {
                    "finding": "hepatic steatosis",
                    "location": "liver",
                    "clinical_significance": "incidental",
                    "recommended_action": "routine follow-up",
                },
            ],
        }
        prompt = build_judge_prompt("Test", gt, "model response")
        assert "hepatic steatosis" in prompt
        assert "routine follow-up" in prompt
        assert "Incidental findings" in prompt
