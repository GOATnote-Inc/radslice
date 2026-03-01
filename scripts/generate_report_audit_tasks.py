#!/usr/bin/env python3
"""Generate report_audit task YAMLs from existing diagnosis tasks.

Given a directory of source diagnosis tasks, generates synthetic radiologist
reports with planted errors and produces report_audit task YAMLs.

Usage:
    python scripts/generate_report_audit_tasks.py \
        --source-dir configs/tasks/ct/ \
        --output-dir configs/tasks/audit/ \
        --n-tasks 5 \
        --dry-run

Error types:
    - missed_finding: Finding present on image but not mentioned in report
    - wrong_laterality: Correct finding but wrong side
    - severity_underestimate: Finding identified but severity understated
    - hallucinated_finding: Report describes finding not present on image
    - wrong_diagnosis: Incorrect diagnostic conclusion
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import yaml

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.task import load_task, load_tasks_from_dir, validate_task, Task

logger = logging.getLogger(__name__)

ALL_ERROR_TYPES = [
    "missed_finding",
    "wrong_laterality",
    "severity_underestimate",
    "hallucinated_finding",
    "wrong_diagnosis",
]

# Templates for generating synthetic reports with errors
REPORT_TEMPLATES = {
    "ct": (
        "CT {anatomy} {contrast}: {technique_detail}. "
        "{findings_text} "
        "IMPRESSION: {impression}"
    ),
    "xray": (
        "PA and lateral {anatomy} radiograph. "
        "{findings_text} "
        "IMPRESSION: {impression}"
    ),
    "mri": (
        "MRI {anatomy} {contrast}: {technique_detail}. "
        "{findings_text} "
        "IMPRESSION: {impression}"
    ),
    "ultrasound": (
        "{anatomy} ultrasound performed. "
        "{findings_text} "
        "IMPRESSION: {impression}"
    ),
}

CONTRAST_OPTIONS = {
    "ct": ["without contrast", "with IV contrast", "with and without contrast"],
    "xray": [""],
    "mri": ["without contrast", "with and without gadolinium"],
    "ultrasound": [""],
}

TECHNIQUE_DETAILS = {
    "ct": [
        "Axial images obtained from the thoracic inlet through the lung bases",
        "Axial images obtained through the abdomen and pelvis",
        "Helical acquisition with 3mm slice thickness",
    ],
    "mri": [
        "Multiplanar multisequence images obtained",
        "T1, T2, FLAIR, and DWI sequences performed",
    ],
}

NORMAL_FINDINGS = {
    "chest": [
        "The heart is normal in size and configuration.",
        "The mediastinum is unremarkable.",
        "No pleural effusion or pneumothorax.",
        "The osseous structures are intact.",
        "No lymphadenopathy.",
    ],
    "abdomen": [
        "The liver, spleen, and pancreas are unremarkable.",
        "No free fluid.",
        "The kidneys are normal in size and attenuation.",
        "The bowel gas pattern is unremarkable.",
        "No lymphadenopathy.",
    ],
    "head": [
        "No acute intracranial hemorrhage.",
        "The ventricles are normal in size.",
        "No midline shift.",
        "The osseous structures are intact.",
    ],
}


def _generate_report_with_error(
    task: Task,
    error_type: str,
    rng: random.Random,
) -> tuple[str, dict]:
    """Generate a synthetic report with one planted error.

    Returns (report_text, error_dict).
    """
    gt = task.ground_truth
    anatomy = task.anatomy
    modality = task.modality

    normal_statements = NORMAL_FINDINGS.get(anatomy, NORMAL_FINDINGS["chest"])

    if error_type == "missed_finding":
        # Report omits the primary finding — says everything is normal
        findings = rng.sample(normal_statements, min(3, len(normal_statements)))
        findings_text = " ".join(findings)
        impression = f"No acute {anatomy} abnormality."
        claim = f"No acute {anatomy} abnormality"
        correction = (
            f"{gt.primary_diagnosis} is present"
            + (f" — {gt.key_findings[0].finding} at {gt.key_findings[0].location}" if gt.key_findings else "")
        )
        severity = "critical"

    elif error_type == "wrong_laterality":
        wrong_side = "left" if gt.laterality == "right" else "right"
        findings = [
            f"{gt.primary_diagnosis.capitalize()} identified on the {wrong_side} side."
        ]
        findings += rng.sample(normal_statements, min(2, len(normal_statements)))
        findings_text = " ".join(findings)
        impression = f"{wrong_side.capitalize()}-sided {gt.primary_diagnosis}."
        claim = f"{wrong_side}-sided {gt.primary_diagnosis}"
        correction = f"{gt.laterality}-sided {gt.primary_diagnosis}"
        severity = "critical"

    elif error_type == "severity_underestimate":
        mild_descriptor = rng.choice(["small", "minimal", "trace", "mild", "subtle"])
        findings = [
            f"{mild_descriptor.capitalize()} {gt.primary_diagnosis} noted."
        ]
        findings += rng.sample(normal_statements, min(2, len(normal_statements)))
        findings_text = " ".join(findings)
        impression = f"{mild_descriptor.capitalize()} {gt.primary_diagnosis}, likely clinically insignificant."
        claim = f"{mild_descriptor} {gt.primary_diagnosis}"
        correction = f"{gt.severity} {gt.primary_diagnosis}" if gt.severity else f"Significant {gt.primary_diagnosis}"
        severity = "major"

    elif error_type == "hallucinated_finding":
        # Report describes a finding that is in the negatives list
        if gt.negatives:
            hallucinated = rng.choice(gt.negatives)
        else:
            hallucinated = rng.choice(["mass", "effusion", "fracture"])
        findings = [f"{hallucinated.capitalize()} identified."]
        findings += rng.sample(normal_statements, min(2, len(normal_statements)))
        findings_text = " ".join(findings)
        impression = f"{hallucinated.capitalize()} requiring further evaluation."
        claim = f"{hallucinated} identified"
        correction = f"No {hallucinated} is present"
        severity = "critical"

    elif error_type == "wrong_diagnosis":
        # Pick from differential if available
        if len(gt.differential) > 1:
            wrong_dx = rng.choice([d for d in gt.differential if d != gt.primary_diagnosis])
        else:
            wrong_dx = f"not {gt.primary_diagnosis}"
        findings = rng.sample(normal_statements, min(2, len(normal_statements)))
        findings_text = " ".join(findings) + f" Findings most consistent with {wrong_dx}."
        impression = f"{wrong_dx.capitalize()}."
        claim = f"Findings consistent with {wrong_dx}"
        correction = f"Findings are consistent with {gt.primary_diagnosis}"
        severity = "critical"

    else:
        raise ValueError(f"Unknown error_type: {error_type}")

    # Assemble full report
    contrast = rng.choice(CONTRAST_OPTIONS.get(modality, [""]))
    technique = rng.choice(TECHNIQUE_DETAILS.get(modality, [""]))
    template = REPORT_TEMPLATES.get(modality, REPORT_TEMPLATES["ct"])
    report = template.format(
        anatomy=anatomy,
        contrast=contrast,
        technique_detail=technique,
        findings_text=findings_text,
        impression=impression,
    )

    error_dict = {
        "error_type": error_type,
        "claim": claim,
        "correction": correction,
        "severity": severity,
    }

    return report, error_dict


def generate_audit_task(
    source_task: Task,
    error_types: list[str],
    rng: random.Random,
    task_id_prefix: str = "AUD",
) -> dict:
    """Generate a report_audit task dict from a source diagnosis task."""
    error_type = rng.choice(error_types)
    report, error_dict = _generate_report_with_error(source_task, error_type, rng)

    task_id = f"{source_task.modality.upper()}-{task_id_prefix}-{source_task.id}"

    # Build pattern checks for the audit task
    pattern_checks = []
    if error_type == "missed_finding":
        pattern_checks.append({
            "name": "identifies_missed_error",
            "check_type": "regex",
            "pattern": r"\b(missed|omitted|not.mentioned|failed.to|absent.from.report)\b",
            "required": True,
        })
    elif error_type == "wrong_laterality":
        pattern_checks.append({
            "name": "identifies_laterality_error",
            "check_type": "regex",
            "pattern": r"\b(wrong.side|laterality|incorrect.side|contralateral)\b",
            "required": True,
        })
    elif error_type == "severity_underestimate":
        pattern_checks.append({
            "name": "identifies_severity_error",
            "check_type": "regex",
            "pattern": r"\b(underestimat|understated|underrated|more.severe|significant)\b",
            "required": True,
        })
    elif error_type == "hallucinated_finding":
        pattern_checks.append({
            "name": "identifies_hallucination",
            "check_type": "regex",
            "pattern": r"\b(hallucinated|fabricated|not.present|false.positive|overcall)\b",
            "required": True,
        })
    elif error_type == "wrong_diagnosis":
        pattern_checks.append({
            "name": "identifies_wrong_diagnosis",
            "check_type": "regex",
            "pattern": r"\b(wrong|incorrect|misdiagnos|should.be)\b",
            "required": True,
        })

    # Always check that the model identifies there IS an error
    pattern_checks.append({
        "name": "identifies_error_present",
        "check_type": "regex",
        "pattern": r"\b(error|mistake|incorrect|discrepancy|inaccura)\b",
        "required": True,
    })

    gt_dict = {
        "primary_diagnosis": source_task.ground_truth.primary_diagnosis,
        "differential": list(source_task.ground_truth.differential),
        "severity": source_task.ground_truth.severity,
        "laterality": source_task.ground_truth.laterality,
        "provided_report": report,
        "report_errors": [error_dict],
    }

    if source_task.ground_truth.key_findings:
        gt_dict["key_findings"] = [
            {
                "finding": kf.finding,
                "location": kf.location,
                "required": kf.required,
            }
            for kf in source_task.ground_truth.key_findings
        ]

    return {
        "id": task_id,
        "name": f"Report audit: {error_type.replace('_', ' ')} — {source_task.name}",
        "modality": source_task.modality,
        "anatomy": source_task.anatomy,
        "task_type": "report_audit",
        "difficulty": "advanced",
        "image_ref": source_task.image_ref,
        "prompt_template": "report_audit",
        "ground_truth": gt_dict,
        "pattern_checks": pattern_checks,
        "condition_id": source_task.condition_id,
        "source_dataset": "synthetic",
        "tags": ["audit", "generated", error_type],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate report_audit task YAMLs from source diagnosis tasks."
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Directory containing source diagnosis task YAMLs",
    )
    parser.add_argument(
        "--output-dir",
        default="configs/tasks/audit",
        help="Output directory for generated audit tasks (default: configs/tasks/audit)",
    )
    parser.add_argument(
        "--n-tasks",
        type=int,
        default=5,
        help="Number of audit tasks to generate (default: 5)",
    )
    parser.add_argument(
        "--error-types",
        nargs="+",
        choices=ALL_ERROR_TYPES,
        default=ALL_ERROR_TYPES,
        help="Error types to include (default: all)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tasks to stdout without writing files",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    # Load source tasks (only diagnosis type)
    all_tasks = load_tasks_from_dir(source_dir)
    source_tasks = [t for t in all_tasks if t.task_type == "diagnosis"]

    if not source_tasks:
        logger.error("No diagnosis tasks found in %s", source_dir)
        sys.exit(1)

    logger.info("Found %d source diagnosis tasks", len(source_tasks))

    rng = random.Random(args.seed)
    n = min(args.n_tasks, len(source_tasks))

    selected = rng.sample(source_tasks, n)
    output_dir = Path(args.output_dir)

    for source in selected:
        audit_dict = generate_audit_task(source, args.error_types, rng)

        if args.dry_run:
            print(f"--- {audit_dict['id']} ---")
            print(yaml.dump(audit_dict, default_flow_style=False, sort_keys=False))
            print()
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{audit_dict['id']}.yaml"
            with open(path, "w") as f:
                yaml.dump(audit_dict, f, default_flow_style=False, sort_keys=False)
            logger.info("Wrote %s", path)

    logger.info("Generated %d audit tasks (dry_run=%s)", n, args.dry_run)


if __name__ == "__main__":
    main()
