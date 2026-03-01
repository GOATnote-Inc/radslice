"""Tests for report_audit task type: loading, validation, report injection, judge prompt."""

from __future__ import annotations

import pytest
import yaml

from radslice.executor import PROMPT_TEMPLATES, _build_prompt
from radslice.grading.judge import (
    JUDGE_SYSTEM_PROMPT_REPORT_AUDIT,
    build_judge_prompt,
)
from radslice.grading.patterns import run_task_patterns
from radslice.task import (
    GroundTruth,
    KeyFinding,
    PatternCheck,
    ReportError,
    Task,
    TaskValidationError,
    load_task,
    validate_task,
)


class TestReportAuditSchema:
    """Tests for report_audit dataclass and validation."""

    def test_report_error_frozen(self):
        err = ReportError(
            error_type="missed_finding",
            claim="Lungs are clear",
            correction="12mm nodule in RUL",
            severity="critical",
        )
        assert err.error_type == "missed_finding"
        with pytest.raises(AttributeError):
            err.claim = "changed"  # type: ignore[misc]

    def test_ground_truth_with_report_errors(self):
        gt = GroundTruth(
            primary_diagnosis="pulmonary nodule",
            provided_report="Normal chest CT.",
            report_errors=[
                ReportError(
                    error_type="missed_finding",
                    claim="Normal chest CT",
                    correction="12mm nodule in RUL",
                    severity="critical",
                ),
            ],
        )
        assert len(gt.report_errors) == 1
        assert gt.provided_report == "Normal chest CT."

    def test_valid_report_audit_task(self, sample_report_audit_task):
        errors = validate_task(sample_report_audit_task)
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_report_audit_requires_provided_report(self):
        task = Task(
            id="CT-AUD-BAD1",
            name="Bad audit task",
            modality="ct",
            anatomy="chest",
            task_type="report_audit",
            difficulty="basic",
            image_ref="ct/test.png",
            prompt_template="report_audit",
            ground_truth=GroundTruth(
                primary_diagnosis="pulmonary nodule",
                # No provided_report!
                report_errors=[
                    ReportError(
                        error_type="missed_finding",
                        claim="clear",
                        correction="nodule",
                        severity="critical",
                    ),
                ],
            ),
            condition_id="pulmonary-nodule",
        )
        errors = validate_task(task)
        assert any("provided_report" in e for e in errors)

    def test_report_audit_requires_report_errors(self):
        task = Task(
            id="CT-AUD-BAD2",
            name="Bad audit task",
            modality="ct",
            anatomy="chest",
            task_type="report_audit",
            difficulty="basic",
            image_ref="ct/test.png",
            prompt_template="report_audit",
            ground_truth=GroundTruth(
                primary_diagnosis="pulmonary nodule",
                provided_report="Normal chest CT.",
                # No report_errors!
            ),
            condition_id="pulmonary-nodule",
        )
        errors = validate_task(task)
        assert any("report_errors" in e for e in errors)

    def test_report_audit_task_type_valid(self):
        from radslice.task import VALID_TASK_TYPES

        assert "report_audit" in VALID_TASK_TYPES


class TestReportAuditLoading:
    """Tests for loading report_audit tasks from YAML."""

    def test_load_report_audit_yaml(self, tmp_path):
        task_data = {
            "id": "CT-AUD-LOAD",
            "name": "Load test audit",
            "modality": "ct",
            "anatomy": "chest",
            "task_type": "report_audit",
            "difficulty": "advanced",
            "image_ref": "ct/test.png",
            "prompt_template": "report_audit",
            "ground_truth": {
                "primary_diagnosis": "pulmonary nodule",
                "provided_report": "CT chest: The lungs are clear. Normal exam.",
                "report_errors": [
                    {
                        "error_type": "missed_finding",
                        "claim": "The lungs are clear",
                        "correction": "12mm nodule in RUL",
                        "severity": "critical",
                    },
                ],
            },
            "condition_id": "pulmonary-nodule",
        }
        path = tmp_path / "CT-AUD-LOAD.yaml"
        with open(path, "w") as f:
            yaml.dump(task_data, f)

        task = load_task(path)
        assert task.task_type == "report_audit"
        assert task.ground_truth.provided_report == "CT chest: The lungs are clear. Normal exam."
        assert len(task.ground_truth.report_errors) == 1
        assert task.ground_truth.report_errors[0].error_type == "missed_finding"


class TestReportAuditPromptInjection:
    """Tests for report injection into prompt template."""

    def test_report_audit_prompt_template_exists(self):
        assert "report_audit" in PROMPT_TEMPLATES

    def test_build_prompt_injects_report(self, sample_report_audit_task):
        prompt = _build_prompt(sample_report_audit_task)
        assert "Normal chest CT" in prompt
        assert "second-opinion audit" in prompt.lower() or "audit" in prompt.lower()

    def test_build_prompt_contains_report_text(self, sample_report_audit_task):
        prompt = _build_prompt(sample_report_audit_task)
        # The provided report should appear in the prompt
        assert sample_report_audit_task.ground_truth.provided_report in prompt


class TestReportAuditPatternScoring:
    """Tests for pattern check scoring with report audit tasks."""

    def test_patterns_detect_errors(self, sample_report_audit_task):
        good_response = (
            "The report failed to identify a significant finding. "
            "A solitary pulmonary nodule is present in the right upper lobe "
            "that was missed. The report incorrectly states the lungs are clear. "
            "This is a missed finding of moderate severity."
        )
        result = run_task_patterns(sample_report_audit_task, good_response)
        assert result.checks.get("identifies_error_type", False)

    def test_patterns_miss_errors(self, sample_report_audit_task):
        bad_response = (
            "The report appears accurate. No errors identified. "
            "The chest CT is indeed normal."
        )
        result = run_task_patterns(sample_report_audit_task, bad_response)
        assert not result.all_required_pass


class TestReportAuditJudge:
    """Tests for report audit judge prompt construction."""

    def test_report_audit_judge_system_prompt(self):
        assert "audit" in JUDGE_SYSTEM_PROMPT_REPORT_AUDIT.lower()
        assert "planted errors" in JUDGE_SYSTEM_PROMPT_REPORT_AUDIT.lower()
        assert "false_positive_control" in JUDGE_SYSTEM_PROMPT_REPORT_AUDIT
        assert "0.15" in JUDGE_SYSTEM_PROMPT_REPORT_AUDIT  # FP weight

    def test_judge_prompt_includes_report_errors(self):
        gt = {
            "primary_diagnosis": "pulmonary nodule",
            "differential": [],
            "severity": "moderate",
            "laterality": "right",
            "key_findings": [],
            "negatives": [],
            "provided_report": "Normal chest CT.",
            "report_errors": [
                {
                    "error_type": "missed_finding",
                    "claim": "The lungs are clear",
                    "correction": "12mm nodule in RUL",
                    "severity": "critical",
                },
            ],
        }
        prompt = build_judge_prompt("Test", gt, "model response")
        assert "missed_finding" in prompt
        assert "12mm nodule" in prompt
        assert "Normal chest CT" in prompt
        assert "Report errors" in prompt

    def test_judge_prompt_includes_provided_report(self):
        gt = {
            "primary_diagnosis": "test",
            "differential": [],
            "severity": "",
            "laterality": "",
            "key_findings": [],
            "negatives": [],
            "provided_report": "This is the report to audit.",
        }
        prompt = build_judge_prompt("Test", gt, "model response")
        assert "This is the report to audit" in prompt
        assert "Provided Report" in prompt


class TestBackwardCompatibility:
    """Ensure existing tasks work unchanged with new optional fields."""

    def test_existing_diagnosis_task_unaffected(self, sample_task):
        errors = validate_task(sample_task)
        assert errors == []
        assert sample_task.ground_truth.incidental_findings == []
        assert sample_task.ground_truth.report_errors == []
        assert sample_task.ground_truth.provided_report == ""

    def test_existing_yaml_loads_without_new_fields(self, sample_task_yaml):
        task = load_task(sample_task_yaml)
        assert task.task_type == "diagnosis"
        assert task.ground_truth.incidental_findings == []
        assert task.ground_truth.report_errors == []
        assert task.ground_truth.provided_report == ""
