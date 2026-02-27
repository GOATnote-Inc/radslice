"""RubricGrader: 3-layer grading orchestrator for radiology evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from radslice.grading.dimensions import weighted_score
from radslice.grading.judge import JudgeResult, run_judge
from radslice.grading.patterns import (
    PatternResult,
    check_laterality,
    check_negatives,
    run_modality_patterns,
    run_task_patterns,
)
from radslice.providers.base import Provider
from radslice.task import Task

LAYER_0_CONFIDENCE_THRESHOLD = 0.8


@dataclass(frozen=True)
class GradeResult:
    """Complete grading result for a single trial of a task."""

    task_id: str
    model: str
    trial: int
    passed: bool
    weighted_score: float
    dimension_scores: dict[str, float]
    failure_class: str | None  # A, B, C, D, E, or None
    detection_layer: int  # 0 (patterns only) or 2 (judge)
    pattern_result: dict[str, Any] = field(default_factory=dict)
    judge_result: dict[str, Any] = field(default_factory=dict)
    overcalled_negatives: list[str] = field(default_factory=list)
    laterality_correct: bool = True
    modality_signals: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RubricGrader:
    """3-layer radiology grading engine.

    Layer 0: Deterministic pattern checks (fast, free, reproducible).
    Layer 2: LLM radiologist judge (flexible, cross-vendor).

    Judge is only invoked when Layer 0 confidence is below threshold
    or when pattern_only=False.
    """

    def __init__(
        self,
        judge_provider: Provider | None = None,
        judge_model: str = "gpt-5.2",
        pattern_only: bool = False,
    ):
        self._judge_provider = judge_provider
        self._judge_model = judge_model
        self._pattern_only = pattern_only

    async def grade(
        self,
        task: Task,
        response: str,
        model: str,
        trial: int = 0,
    ) -> GradeResult:
        """Grade a model response for a task."""
        # Layer 0: Deterministic patterns
        pattern_result = run_task_patterns(task, response)
        modality_signals = run_modality_patterns(task.modality, response)
        lat_correct = check_laterality(response, task.ground_truth.laterality)
        overcalled = check_negatives(response, task.ground_truth.negatives)

        # Build initial dimension scores from patterns
        dim_scores = self._scores_from_patterns(pattern_result, lat_correct, overcalled, task)
        detection_layer = 0
        judge_data: dict[str, Any] = {}
        failure_class = self._classify_from_patterns(pattern_result, overcalled, response)

        # Layer 2: LLM judge (if needed and available)
        if (
            not self._pattern_only
            and self._judge_provider is not None
            and pattern_result.confidence < LAYER_0_CONFIDENCE_THRESHOLD
        ):
            judge_result = await self._run_judge(task, response)
            if judge_result:
                dim_scores = self._combine_scores(dim_scores, judge_result)
                detection_layer = 2
                failure_class = judge_result.failure_class
                judge_data = {
                    "dimension_scores": judge_result.dimension_scores,
                    "failure_class": judge_result.failure_class,
                    "reasoning": judge_result.reasoning,
                    "judge_model": judge_result.judge_model,
                }

        w_score = weighted_score(dim_scores)
        passed = self._determine_pass(w_score, failure_class)

        return GradeResult(
            task_id=task.id,
            model=model,
            trial=trial,
            passed=passed,
            weighted_score=w_score,
            dimension_scores=dim_scores,
            failure_class=failure_class,
            detection_layer=detection_layer,
            pattern_result={
                "checks": pattern_result.checks,
                "required_passed": pattern_result.required_passed,
                "required_total": pattern_result.required_total,
                "confidence": pattern_result.confidence,
            },
            judge_result=judge_data,
            overcalled_negatives=overcalled,
            laterality_correct=lat_correct,
            modality_signals=modality_signals,
        )

    def _scores_from_patterns(
        self,
        pattern_result: PatternResult,
        lat_correct: bool,
        overcalled: list[str],
        task: Task,
    ) -> dict[str, float]:
        """Derive dimension scores from pattern checks."""
        scores: dict[str, float] = {}

        # diagnostic_accuracy: based on required pattern pass rate
        if pattern_result.required_total > 0:
            scores["diagnostic_accuracy"] = (
                pattern_result.required_passed / pattern_result.required_total
            )
        else:
            scores["diagnostic_accuracy"] = 0.5  # Unknown without patterns

        # finding_detection: based on overall pass rate
        scores["finding_detection"] = pattern_result.pass_rate

        # anatomic_precision: laterality check
        scores["anatomic_precision"] = 1.0 if lat_correct else 0.0

        # clinical_relevance: default 0.5 (patterns can't assess this well)
        scores["clinical_relevance"] = 0.5

        # false_positive_control: penalize overcalls
        if not overcalled:
            scores["false_positive_control"] = 1.0
        else:
            n_negatives = len(task.ground_truth.negatives)
            if n_negatives > 0:
                scores["false_positive_control"] = max(0.0, 1.0 - len(overcalled) / n_negatives)
            else:
                scores["false_positive_control"] = 0.0

        return scores

    def _combine_scores(
        self,
        pattern_scores: dict[str, float],
        judge_result: JudgeResult,
    ) -> dict[str, float]:
        """Combine pattern and judge scores, preferring judge where available."""
        combined = dict(pattern_scores)
        for dim_name, judge_score in judge_result.dimension_scores.items():
            if dim_name in combined:
                # Judge takes precedence for most dimensions
                if dim_name == "false_positive_control":
                    # Use min of pattern and judge (conservative)
                    combined[dim_name] = min(combined[dim_name], judge_score)
                else:
                    combined[dim_name] = judge_score
        return combined

    def _classify_from_patterns(
        self,
        pattern_result: PatternResult,
        overcalled: list[str],
        response: str,
    ) -> str | None:
        """Classify failure from pattern results alone."""
        # Class E: refusal
        refusal_patterns = ["cannot interpret", "unable to analyze", "i cannot", "i'm unable"]
        if any(p in response.lower() for p in refusal_patterns):
            return "E"

        # Class D: overcall/hallucination
        if overcalled:
            return "D"

        # Class A: missed critical diagnosis (all required patterns failed)
        if pattern_result.required_total > 0 and pattern_result.required_passed == 0:
            return "A"

        # Class C: partial (some required patterns failed)
        if not pattern_result.all_required_pass:
            return "C"

        return None

    def _determine_pass(self, score: float, failure_class: str | None) -> bool:
        """Determine pass/fail. Class A and B always fail."""
        if failure_class in ("A", "B"):
            return False
        return score >= 0.5

    async def _run_judge(self, task: Task, response: str) -> JudgeResult | None:
        """Run the LLM judge, returning None on error."""
        if not self._judge_provider:
            return None

        ground_truth = {
            "primary_diagnosis": task.ground_truth.primary_diagnosis,
            "differential": task.ground_truth.differential,
            "severity": task.ground_truth.severity,
            "laterality": task.ground_truth.laterality,
            "key_findings": [
                {"finding": kf.finding, "location": kf.location, "required": kf.required}
                for kf in task.ground_truth.key_findings
            ],
            "negatives": task.ground_truth.negatives,
        }

        try:
            return await run_judge(
                provider=self._judge_provider,
                judge_model=self._judge_model,
                task_name=task.name,
                ground_truth=ground_truth,
                model_response=response,
                reference_solution=task.reference_solution,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Judge failed for %s, falling back to patterns", task.id, exc_info=True
            )
            return None
