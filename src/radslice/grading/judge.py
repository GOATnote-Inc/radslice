"""Layer 2: LLM radiologist judge with cross-vendor grading."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from radslice.providers.base import Provider

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an expert radiologist serving as a grading judge for a radiology AI benchmark. You will evaluate a model's response to a radiology image interpretation task.

Grade the response on these 5 dimensions (each 0.0 to 1.0):

1. **diagnostic_accuracy** (weight 0.35): Is the primary diagnosis correct? Is the differential reasonable?
2. **finding_detection** (weight 0.25): Are the required radiological findings identified with correct anatomic locations?
3. **anatomic_precision** (weight 0.15): Is laterality correct? Are lobes, segments, or anatomic references accurate?
4. **clinical_relevance** (weight 0.15): Is severity appropriately assessed? Are clinical recommendations sensible?
5. **false_positive_control** (weight 0.10): Are there any hallucinated findings or overcalled pathology? (1.0 = no false positives, 0.0 = significant hallucination)

Also classify the failure mode (or null if passing):
- **A**: Missed critical diagnosis (primary diagnosis wrong or absent)
- **B**: Wrong diagnosis (confidently stated incorrect diagnosis)
- **C**: Partial/wrong location (correct diagnosis, wrong laterality or anatomy)
- **D**: Overcall/hallucination (added pathology not present)
- **E**: Refusal (declined to interpret the image)

Respond ONLY with valid JSON:
{
  "diagnostic_accuracy": <float>,
  "finding_detection": <float>,
  "anatomic_precision": <float>,
  "clinical_relevance": <float>,
  "false_positive_control": <float>,
  "failure_class": <string or null>,
  "reasoning": "<brief explanation>"
}"""


@dataclass(frozen=True)
class JudgeResult:
    """Result from LLM radiologist judge."""

    dimension_scores: dict[str, float]
    failure_class: str | None
    reasoning: str = ""
    judge_model: str = ""
    raw_response: str = ""


def build_judge_prompt(
    task_name: str,
    ground_truth: dict[str, Any],
    model_response: str,
    reference_solution: str = "",
) -> str:
    """Build the grading prompt for the LLM judge."""
    parts = [
        f"## Task: {task_name}\n",
        "## Ground Truth:",
        f"- Primary diagnosis: {ground_truth.get('primary_diagnosis', 'N/A')}",
        f"- Differential: {ground_truth.get('differential', [])}",
        f"- Severity: {ground_truth.get('severity', 'N/A')}",
        f"- Laterality: {ground_truth.get('laterality', 'N/A')}",
    ]

    key_findings = ground_truth.get("key_findings", [])
    if key_findings:
        parts.append("- Key findings:")
        for kf in key_findings:
            req = " (required)" if kf.get("required", True) else " (optional)"
            parts.append(f"  - {kf['finding']} at {kf['location']}{req}")

    negatives = ground_truth.get("negatives", [])
    if negatives:
        parts.append(f"- Should NOT be present: {negatives}")

    if reference_solution:
        parts.extend(["", "## Reference Solution:", reference_solution])

    parts.extend(["", "## Model Response to Grade:", model_response])

    return "\n".join(parts)


async def run_judge(
    provider: Provider,
    judge_model: str,
    task_name: str,
    ground_truth: dict[str, Any],
    model_response: str,
    reference_solution: str = "",
) -> JudgeResult:
    """Run the LLM radiologist judge on a model response."""
    prompt = build_judge_prompt(task_name, ground_truth, model_response, reference_solution)

    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    response = await provider.complete(
        messages=messages,
        model=judge_model,
        temperature=0.0,
        max_tokens=1024,
    )

    return parse_judge_response(response.text, judge_model)


def parse_judge_response(text: str, judge_model: str = "") -> JudgeResult:
    """Parse the judge's JSON response into a JudgeResult."""
    # Try to extract JSON from the response
    try:
        # Handle markdown code blocks
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (code block markers)
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                if line.strip() == "```" and in_block:
                    break
                if in_block:
                    json_lines.append(line)
            cleaned = "\n".join(json_lines)

        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse judge response as JSON: %s", text[:200])
        return JudgeResult(
            dimension_scores={
                "diagnostic_accuracy": 0.0,
                "finding_detection": 0.0,
                "anatomic_precision": 0.0,
                "clinical_relevance": 0.0,
                "false_positive_control": 0.0,
            },
            failure_class="E",
            reasoning="Judge response was not valid JSON",
            judge_model=judge_model,
            raw_response=text,
        )

    dimension_names = [
        "diagnostic_accuracy",
        "finding_detection",
        "anatomic_precision",
        "clinical_relevance",
        "false_positive_control",
    ]

    scores = {}
    for name in dimension_names:
        val = data.get(name, 0.0)
        scores[name] = max(0.0, min(1.0, float(val)))

    failure_class = data.get("failure_class")
    if failure_class and failure_class not in ("A", "B", "C", "D", "E"):
        failure_class = None

    return JudgeResult(
        dimension_scores=scores,
        failure_class=failure_class,
        reasoning=data.get("reasoning", ""),
        judge_model=judge_model,
        raw_response=text,
    )
