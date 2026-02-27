"""Tests for grading — patterns, dimensions, grader, judge parsing."""

from __future__ import annotations

import pytest

from radslice.grading.dimensions import DIMENSIONS, weighted_score
from radslice.grading.grader import GradeResult, RubricGrader
from radslice.grading.judge import JudgeResult, build_judge_prompt, parse_judge_response
from radslice.grading.patterns import (
    PatternResult,
    check_laterality,
    check_negatives,
    run_modality_patterns,
    run_task_patterns,
)

# --- Dimensions ---


class TestDimensions:
    def test_five_dimensions(self):
        assert len(DIMENSIONS) == 5

    def test_weights_sum_to_one(self):
        total = sum(d.weight for d in DIMENSIONS)
        assert total == pytest.approx(1.0)

    def test_dimension_names(self):
        names = {d.name for d in DIMENSIONS}
        assert "diagnostic_accuracy" in names
        assert "finding_detection" in names
        assert "anatomic_precision" in names
        assert "clinical_relevance" in names
        assert "false_positive_control" in names

    def test_frozen(self):
        dim = DIMENSIONS[0]
        with pytest.raises(AttributeError):
            dim.weight = 0.5

    def test_weighted_score_perfect(self):
        scores = {d.name: 1.0 for d in DIMENSIONS}
        assert weighted_score(scores) == pytest.approx(1.0)

    def test_weighted_score_zero(self):
        scores = {d.name: 0.0 for d in DIMENSIONS}
        assert weighted_score(scores) == pytest.approx(0.0)

    def test_weighted_score_partial(self):
        scores = {"diagnostic_accuracy": 1.0, "finding_detection": 0.0}
        score = weighted_score(scores)
        assert 0.0 < score < 1.0

    def test_weighted_score_empty(self):
        assert weighted_score({}) == 0.0


# --- Patterns ---


class TestRunTaskPatterns:
    def test_good_response(self, sample_task, good_response):
        result = run_task_patterns(sample_task, good_response)
        assert isinstance(result, PatternResult)
        assert result.all_required_pass is True
        assert result.required_passed == result.required_total

    def test_bad_response(self, sample_task, bad_response):
        result = run_task_patterns(sample_task, bad_response)
        assert result.all_required_pass is False
        assert result.required_passed < result.required_total

    def test_confidence_high_when_all_pass(self, sample_task, good_response):
        result = run_task_patterns(sample_task, good_response)
        assert result.confidence >= 0.8

    def test_confidence_high_when_all_fail(self, sample_task, bad_response):
        result = run_task_patterns(sample_task, bad_response)
        assert result.confidence >= 0.5

    def test_pass_rate(self, sample_task, good_response):
        result = run_task_patterns(sample_task, good_response)
        assert result.pass_rate == pytest.approx(1.0)


class TestModalityPatterns:
    def test_xray_patterns(self):
        text = "There is consolidation in the right lower lobe with pleural effusion."
        results = run_modality_patterns("xray", text)
        assert results.get("consolidation") is True
        assert results.get("effusion") is True

    def test_ct_patterns(self):
        text = "Hyperdense hemorrhage with surrounding mass effect."
        results = run_modality_patterns("ct", text)
        assert results.get("hemorrhage") is True
        assert results.get("mass_effect") is True

    def test_mri_patterns(self):
        text = "T2 hyperintense signal with diffusion restriction on DWI."
        results = run_modality_patterns("mri", text)
        assert results.get("t2_signal") is True
        assert results.get("diffusion_restriction") is True

    def test_us_patterns(self):
        text = "Hyperechoic focus with posterior acoustic shadowing."
        results = run_modality_patterns("ultrasound", text)
        assert results.get("echogenicity") is True
        assert results.get("shadowing") is True

    def test_unknown_modality(self):
        results = run_modality_patterns("unknown", "test text")
        assert results == {}


class TestCheckLaterality:
    def test_correct(self):
        assert check_laterality("Left-sided pneumothorax", "left") is True

    def test_incorrect(self):
        assert check_laterality("Right-sided effusion", "left") is False

    def test_empty_expected(self):
        assert check_laterality("some text", "") is True


class TestCheckNegatives:
    def test_no_overcalls(self):
        assert check_negatives("Simple pneumothorax", ["tension pneumothorax"]) == []

    def test_overcall_detected(self):
        result = check_negatives(
            "Tension pneumothorax identified",
            ["tension pneumothorax"],
        )
        assert "tension pneumothorax" in result

    def test_multiple_overcalls(self):
        result = check_negatives(
            "Tension pneumothorax and right-sided pneumothorax noted",
            ["tension pneumothorax", "right-sided pneumothorax"],
        )
        assert len(result) == 2


# --- Judge parsing ---


class TestParseJudgeResponse:
    def test_valid_json(self):
        text = """
        {
            "diagnostic_accuracy": 0.9,
            "finding_detection": 0.8,
            "anatomic_precision": 0.85,
            "clinical_relevance": 0.7,
            "false_positive_control": 0.95,
            "failure_class": null,
            "reasoning": "Good response"
        }
        """
        result = parse_judge_response(text, "test-judge")
        assert isinstance(result, JudgeResult)
        assert result.dimension_scores["diagnostic_accuracy"] == 0.9
        assert result.failure_class is None
        assert result.reasoning == "Good response"
        assert result.judge_model == "test-judge"

    def test_markdown_code_block(self):
        text = """```json
        {
            "diagnostic_accuracy": 0.5,
            "finding_detection": 0.5,
            "anatomic_precision": 0.5,
            "clinical_relevance": 0.5,
            "false_positive_control": 0.5,
            "failure_class": "A",
            "reasoning": "Missed diagnosis"
        }
        ```"""
        result = parse_judge_response(text)
        assert result.dimension_scores["diagnostic_accuracy"] == 0.5
        assert result.failure_class == "A"

    def test_invalid_json(self):
        result = parse_judge_response("not json at all")
        assert result.failure_class == "E"
        assert all(v == 0.0 for v in result.dimension_scores.values())

    def test_scores_clamped(self):
        text = '{"diagnostic_accuracy": 1.5, "finding_detection": -0.5, "anatomic_precision": 0.5, "clinical_relevance": 0.5, "false_positive_control": 0.5, "failure_class": null}'
        result = parse_judge_response(text)
        assert result.dimension_scores["diagnostic_accuracy"] == 1.0
        assert result.dimension_scores["finding_detection"] == 0.0

    def test_invalid_failure_class_ignored(self):
        text = '{"diagnostic_accuracy": 0.5, "finding_detection": 0.5, "anatomic_precision": 0.5, "clinical_relevance": 0.5, "false_positive_control": 0.5, "failure_class": "X"}'
        result = parse_judge_response(text)
        assert result.failure_class is None


class TestBuildJudgePrompt:
    def test_includes_ground_truth(self):
        prompt = build_judge_prompt(
            "Test Task",
            {"primary_diagnosis": "pneumothorax", "differential": ["ptx"]},
            "model said something",
        )
        assert "pneumothorax" in prompt
        assert "model said something" in prompt

    def test_includes_reference(self):
        prompt = build_judge_prompt(
            "Test",
            {"primary_diagnosis": "test"},
            "response",
            reference_solution="reference text",
        )
        assert "reference text" in prompt

    def test_includes_negatives(self):
        prompt = build_judge_prompt(
            "Test",
            {"primary_diagnosis": "test", "negatives": ["tension ptx"]},
            "response",
        )
        assert "tension ptx" in prompt


# --- RubricGrader ---


class TestRubricGrader:
    @pytest.mark.asyncio
    async def test_pattern_only_pass(self, sample_task, good_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, good_response, "test-model", trial=0)
        assert isinstance(result, GradeResult)
        assert result.passed is True
        assert result.detection_layer == 0
        assert result.task_id == "XRAY-001"

    @pytest.mark.asyncio
    async def test_pattern_only_partial(self, sample_task, bad_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, bad_response, "test-model", trial=0)
        # Bad response mentions "pneumothorax" (regex matches negation too)
        # but fails laterality — classified as Class C (partial)
        assert result.failure_class == "C"
        assert result.laterality_correct is False

    @pytest.mark.asyncio
    async def test_pattern_only_total_fail(self, sample_task):
        # Response mentions tension pneumothorax (overcall) which fails the
        # not_contains check, and doesn't mention left or pneumothorax correctly
        response = "Tension pneumothorax on the right side requiring emergent decompression."
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, response, "test-model", trial=0)
        assert result.passed is False
        # Should be Class D (overcall) since it mentions "tension pneumothorax"
        assert result.failure_class == "D"

    @pytest.mark.asyncio
    async def test_overcall_detected(self, sample_task):
        response = "Left tension pneumothorax identified."
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, response, "test-model")
        assert "tension pneumothorax" in result.overcalled_negatives
        assert result.failure_class == "D"

    @pytest.mark.asyncio
    async def test_laterality_check(self, sample_task, good_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, good_response, "test-model")
        assert result.laterality_correct is True

    @pytest.mark.asyncio
    async def test_refusal_detected(self, sample_task):
        response = "I cannot interpret medical images. Please consult a radiologist."
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, response, "test-model")
        assert result.failure_class == "E"
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_grade_result_frozen(self, sample_task, good_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, good_response, "test-model")
        with pytest.raises(AttributeError):
            result.passed = False

    @pytest.mark.asyncio
    async def test_grade_result_to_dict(self, sample_task, good_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, good_response, "test-model")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["task_id"] == "XRAY-001"
        assert "dimension_scores" in d
        assert "pattern_result" in d

    @pytest.mark.asyncio
    async def test_modality_signals_included(self, sample_task, good_response):
        grader = RubricGrader(pattern_only=True)
        result = await grader.grade(sample_task, good_response, "test-model")
        assert isinstance(result.modality_signals, dict)
        # X-ray modality signals should be present
        assert "pneumothorax" in result.modality_signals
