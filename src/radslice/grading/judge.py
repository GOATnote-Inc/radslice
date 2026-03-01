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


JUDGE_SYSTEM_PROMPT_INCIDENTAL = """You are an expert radiologist serving as a grading judge for a radiology AI benchmark. You will evaluate a model's response to an incidental finding detection task.

The model was shown a medical image and asked to identify the primary pathology AND all incidental/secondary findings, then triage each by clinical significance.

Grade the response on these 5 dimensions (each 0.0 to 1.0):

1. **diagnostic_accuracy** (weight 0.25): Is the primary diagnosis correct?
2. **finding_detection** (weight 0.35): Are incidental findings identified? Are critical incidentals caught?
3. **anatomic_precision** (weight 0.15): Are finding locations correct?
4. **clinical_relevance** (weight 0.15): Is clinical significance triage appropriate? Are recommended actions sensible?
5. **false_positive_control** (weight 0.10): Are there hallucinated findings? (1.0 = no false positives)

Also classify the failure mode (or null if passing):
- **A**: Missed critical incidental finding (e.g., missed pulmonary nodule on abdominal CT)
- **B**: Wrong significance triage (critical finding called benign, or vice versa)
- **C**: Wrong location for a correctly identified finding
- **D**: Overcall/hallucination (reported finding not present)
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

JUDGE_SYSTEM_PROMPT_REPORT_AUDIT = """You are an expert radiologist serving as a grading judge for a radiology AI benchmark. You will evaluate a model's performance on a report audit task.

The model was shown a medical image AND a radiologist's report containing planted errors. The model was asked to identify errors in the report.

Grade the response on these 5 dimensions (each 0.0 to 1.0):

1. **diagnostic_accuracy** (weight 0.30): Did the model correctly identify the errors in the report?
2. **finding_detection** (weight 0.30): Were all planted errors detected? (sensitivity)
3. **anatomic_precision** (weight 0.10): Are error descriptions anatomically precise?
4. **clinical_relevance** (weight 0.15): Are error severity classifications appropriate? Are corrections clinically sound?
5. **false_positive_control** (weight 0.15): Did the model flag correct report statements as errors? (1.0 = no false alarms)

Also classify the failure mode (or null if passing):
- **A**: Missed a critical error (e.g., didn't flag a missed pneumothorax)
- **B**: Wrong error classification (called a laterality error a missed finding, etc.)
- **C**: Identified error but gave wrong correction
- **D**: False alarm (flagged a correct statement as an error)
- **E**: Refusal (declined to audit the report)

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

    incidental_findings = ground_truth.get("incidental_findings", [])
    if incidental_findings:
        parts.append("- Incidental findings (ground truth):")
        for inc in incidental_findings:
            parts.append(
                f"  - {inc['finding']} at {inc['location']} "
                f"[{inc['clinical_significance']}] → {inc['recommended_action']}"
            )

    report_errors = ground_truth.get("report_errors", [])
    if report_errors:
        parts.append("- Report errors (planted):")
        for err in report_errors:
            parts.append(
                f"  - [{err['error_type']}] ({err['severity']}): "
                f'Report says: "{err["claim"]}" → Should be: "{err["correction"]}"'
            )

    provided_report = ground_truth.get("provided_report", "")
    if provided_report:
        parts.extend(["", "## Provided Report (being audited):", provided_report])

    if reference_solution:
        parts.extend(["", "## Reference Solution:", reference_solution])

    parts.extend(["", "## Model Response to Grade:", model_response])

    return "\n".join(parts)


_JUDGE_PROMPTS_BY_TASK_TYPE = {
    "incidental_detection": JUDGE_SYSTEM_PROMPT_INCIDENTAL,
    "report_audit": JUDGE_SYSTEM_PROMPT_REPORT_AUDIT,
}


async def run_judge(
    provider: Provider,
    judge_model: str,
    task_name: str,
    ground_truth: dict[str, Any],
    model_response: str,
    reference_solution: str = "",
    task_type: str = "",
) -> JudgeResult:
    """Run the LLM radiologist judge on a model response."""
    prompt = build_judge_prompt(task_name, ground_truth, model_response, reference_solution)

    system_prompt = _JUDGE_PROMPTS_BY_TASK_TYPE.get(task_type, JUDGE_SYSTEM_PROMPT)

    messages = [
        {"role": "system", "content": system_prompt},
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
