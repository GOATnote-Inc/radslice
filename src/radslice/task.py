"""Frozen Task dataclass and YAML loader for radiology evaluation tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# --- Nested frozen dataclasses ---


@dataclass(frozen=True)
class KeyFinding:
    """A single radiological finding with location."""

    finding: str
    location: str
    required: bool = True


@dataclass(frozen=True)
class GroundTruth:
    """Ground truth for a radiology task."""

    primary_diagnosis: str
    differential: list[str] = field(default_factory=list)
    key_findings: list[KeyFinding] = field(default_factory=list)
    severity: str = ""
    laterality: str = ""
    negatives: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PatternCheck:
    """A deterministic pattern check defined in the task YAML."""

    name: str
    check_type: str  # regex | contains | not_contains
    pattern: str
    required: bool = True

    def check(self, text: str) -> bool:
        """Run this pattern check against text. Returns True if check passes."""
        text_lower = text.lower()
        if self.check_type == "regex":
            return bool(re.search(self.pattern, text, re.IGNORECASE))
        elif self.check_type == "contains":
            return self.pattern.lower() in text_lower
        elif self.check_type == "not_contains":
            return self.pattern.lower() not in text_lower
        else:
            raise ValueError(f"Unknown check_type: {self.check_type}")


@dataclass(frozen=True)
class Task:
    """A single radiology evaluation task. Immutable after loading."""

    id: str
    name: str
    modality: str  # xray | ct | mri | ultrasound
    anatomy: str
    task_type: str  # diagnosis | finding_detection | vqa | report_generation
    difficulty: str  # basic | intermediate | advanced | expert
    image_ref: str
    prompt_template: str
    ground_truth: GroundTruth
    pattern_checks: list[PatternCheck] = field(default_factory=list)
    reference_solution: str = ""
    condition_present: bool = True
    confusion_pair: str | None = None
    condition_id: str = ""  # OpenEM condition identifier (e.g. "spontaneous-pneumothorax")
    lostbench_scenario_id: str = ""  # LostBench scenario ID (e.g. "MTR-016") if applicable
    source_dataset: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def run_pattern_checks(self, text: str) -> dict[str, bool]:
        """Run all pattern checks against text. Returns {name: passed}."""
        return {pc.name: pc.check(text) for pc in self.pattern_checks}

    def required_pattern_checks_pass(self, text: str) -> bool:
        """Return True if all required pattern checks pass."""
        return all(pc.check(text) for pc in self.pattern_checks if pc.required)


VALID_MODALITIES = {"xray", "ct", "mri", "ultrasound"}
VALID_TASK_TYPES = {"diagnosis", "finding_detection", "vqa", "report_generation"}
VALID_DIFFICULTIES = {"basic", "intermediate", "advanced", "expert"}


def _parse_key_findings(raw: list[dict]) -> list[KeyFinding]:
    return [
        KeyFinding(
            finding=f["finding"],
            location=f["location"],
            required=f.get("required", True),
        )
        for f in raw
    ]


def _parse_ground_truth(raw: dict) -> GroundTruth:
    return GroundTruth(
        primary_diagnosis=raw["primary_diagnosis"],
        differential=raw.get("differential", []),
        key_findings=_parse_key_findings(raw.get("key_findings", [])),
        severity=raw.get("severity", ""),
        laterality=raw.get("laterality", ""),
        negatives=raw.get("negatives", []),
    )


def _parse_pattern_checks(raw: list[dict]) -> list[PatternCheck]:
    return [
        PatternCheck(
            name=pc["name"],
            check_type=pc["check_type"],
            pattern=pc["pattern"],
            required=pc.get("required", True),
        )
        for pc in raw
    ]


class TaskValidationError(ValueError):
    """Raised when a task YAML fails validation."""

    pass


def validate_task(task: Task) -> list[str]:
    """Validate a task and return list of error messages (empty = valid)."""
    errors = []
    if not task.id:
        errors.append("Task id is required")
    if task.modality not in VALID_MODALITIES:
        errors.append(f"Invalid modality '{task.modality}', must be one of {VALID_MODALITIES}")
    if task.task_type not in VALID_TASK_TYPES:
        errors.append(f"Invalid task_type '{task.task_type}', must be one of {VALID_TASK_TYPES}")
    if task.difficulty not in VALID_DIFFICULTIES:
        errors.append(
            f"Invalid difficulty '{task.difficulty}', must be one of {VALID_DIFFICULTIES}"
        )
    if not task.image_ref:
        errors.append("image_ref is required")
    if not task.ground_truth.primary_diagnosis:
        errors.append("ground_truth.primary_diagnosis is required")
    if not task.condition_id:
        errors.append("condition_id is required (must reference an OpenEM condition)")
    # Validate pattern check types
    for pc in task.pattern_checks:
        if pc.check_type not in {"regex", "contains", "not_contains"}:
            errors.append(f"Invalid check_type '{pc.check_type}' in pattern '{pc.name}'")
    return errors


def load_task(path: str | Path) -> Task:
    """Load a single task from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    task = Task(
        id=raw["id"],
        name=raw["name"],
        modality=raw["modality"],
        anatomy=raw["anatomy"],
        task_type=raw["task_type"],
        difficulty=raw["difficulty"],
        image_ref=raw["image_ref"],
        prompt_template=raw.get("prompt_template", "diagnosis"),
        ground_truth=_parse_ground_truth(raw["ground_truth"]),
        pattern_checks=_parse_pattern_checks(raw.get("pattern_checks", [])),
        reference_solution=raw.get("reference_solution", ""),
        condition_present=raw.get("condition_present", True),
        confusion_pair=raw.get("confusion_pair"),
        condition_id=raw.get("condition_id", ""),
        lostbench_scenario_id=raw.get("lostbench_scenario_id", ""),
        source_dataset=raw.get("source_dataset", ""),
        tags=raw.get("tags", []),
        metadata=raw.get("metadata", {}),
    )

    errors = validate_task(task)
    if errors:
        raise TaskValidationError(f"Task {path}: {'; '.join(errors)}")

    return task


def load_tasks_from_dir(directory: str | Path) -> list[Task]:
    """Load all task YAMLs from a directory (recursive). Sorted by ID."""
    directory = Path(directory)
    tasks = []
    for path in sorted(directory.rglob("*.yaml")):
        tasks.append(load_task(path))
    tasks.sort(key=lambda t: t.id)
    return tasks


def load_tasks_by_modality(
    directory: str | Path, modality: str | None = None
) -> dict[str, list[Task]]:
    """Load tasks grouped by modality. Optionally filter to one modality."""
    tasks = load_tasks_from_dir(directory)
    grouped: dict[str, list[Task]] = {}
    for task in tasks:
        if modality and task.modality != modality:
            continue
        grouped.setdefault(task.modality, []).append(task)
    return grouped
