"""Shared test fixtures for RadSlice."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from radslice.task import GroundTruth, KeyFinding, PatternCheck, Task


@pytest.fixture
def sample_task() -> Task:
    """A minimal task for testing."""
    return Task(
        id="XRAY-001",
        name="Left pneumothorax on PA CXR",
        modality="xray",
        anatomy="chest",
        task_type="diagnosis",
        difficulty="intermediate",
        image_ref="xray/omnimedvqa/CXR_0042.png",
        prompt_template="diagnosis",
        ground_truth=GroundTruth(
            primary_diagnosis="pneumothorax",
            differential=["pneumothorax", "bullous emphysema"],
            key_findings=[
                KeyFinding(
                    finding="visceral pleural line", location="left hemithorax", required=True
                ),
                KeyFinding(finding="absent lung markings", location="left lateral", required=True),
                KeyFinding(finding="no mediastinal shift", location="mediastinum", required=False),
            ],
            severity="moderate",
            laterality="left",
            negatives=["tension pneumothorax", "right-sided pneumothorax"],
        ),
        pattern_checks=[
            PatternCheck(
                name="identifies_pneumothorax",
                check_type="regex",
                pattern=r"\b(pneumothorax|ptx)\b",
                required=True,
            ),
            PatternCheck(
                name="identifies_laterality",
                check_type="regex",
                pattern=r"\b(left|left-sided)\b",
                required=True,
            ),
            PatternCheck(
                name="no_tension_overcall",
                check_type="not_contains",
                pattern="tension pneumothorax",
                required=True,
            ),
        ],
        reference_solution="PA chest radiograph: left-sided simple pneumothorax.",
        condition_present=True,
        confusion_pair="XRAY-043",
        source_dataset="omnimedvqa-open",
        tags=["thoracic", "emergency"],
    )


@pytest.fixture
def sample_task_yaml(tmp_path) -> Path:
    """Create a sample task YAML file and return its path."""
    task_data = {
        "id": "XRAY-TEST",
        "name": "Test Task",
        "modality": "xray",
        "anatomy": "chest",
        "task_type": "diagnosis",
        "difficulty": "basic",
        "image_ref": "xray/test/test.png",
        "prompt_template": "diagnosis",
        "ground_truth": {
            "primary_diagnosis": "pneumonia",
            "differential": ["pneumonia", "atelectasis"],
            "key_findings": [
                {"finding": "consolidation", "location": "right lower lobe", "required": True},
            ],
            "severity": "moderate",
            "laterality": "right",
            "negatives": ["pneumothorax"],
        },
        "pattern_checks": [
            {
                "name": "finds_pneumonia",
                "check_type": "regex",
                "pattern": r"\bpneumonia\b",
                "required": True,
            },
            {
                "name": "finds_laterality",
                "check_type": "contains",
                "pattern": "right",
                "required": True,
            },
        ],
        "reference_solution": "Right lower lobe pneumonia.",
        "condition_present": True,
        "source_dataset": "test",
        "tags": ["test"],
    }
    path = tmp_path / "XRAY-TEST.yaml"
    with open(path, "w") as f:
        yaml.dump(task_data, f)
    return path


@pytest.fixture
def sample_tasks_dir(tmp_path) -> Path:
    """Create a directory with multiple task YAMLs."""
    tasks_dir = tmp_path / "tasks" / "xray"
    tasks_dir.mkdir(parents=True)

    for i in range(5):
        task_data = {
            "id": f"XRAY-T{i:03d}",
            "name": f"Test Task {i}",
            "modality": "xray",
            "anatomy": "chest",
            "task_type": "diagnosis",
            "difficulty": "basic",
            "image_ref": f"xray/test/test_{i}.png",
            "prompt_template": "diagnosis",
            "ground_truth": {
                "primary_diagnosis": f"condition_{i}",
                "differential": [f"condition_{i}"],
                "severity": "moderate",
                "laterality": "right" if i % 2 == 0 else "left",
                "negatives": [],
            },
            "pattern_checks": [
                {
                    "name": f"check_{i}",
                    "check_type": "contains",
                    "pattern": f"condition_{i}",
                    "required": True,
                },
            ],
            "condition_present": True,
            "source_dataset": "test",
            "tags": ["test"],
        }
        with open(tasks_dir / f"XRAY-T{i:03d}.yaml", "w") as f:
            yaml.dump(task_data, f)

    return tmp_path / "tasks"


@pytest.fixture
def good_response() -> str:
    """A model response that should pass for XRAY-001."""
    return (
        "PA chest radiograph demonstrates a left-sided pneumothorax. "
        "There is a visible visceral pleural line in the left hemithorax "
        "with absent lung markings lateral to this line. "
        "No mediastinal shift is identified, suggesting a simple (non-tension) "
        "pneumothorax. The right lung appears clear. "
        "Recommend clinical correlation and possible chest tube placement."
    )


@pytest.fixture
def bad_response() -> str:
    """A model response that should fail for XRAY-001."""
    return (
        "The chest radiograph appears normal with no acute cardiopulmonary disease. "
        "The lungs are clear bilaterally. Heart size is normal. "
        "No pleural effusion or pneumothorax identified."
    )


@pytest.fixture
def tmp_cache_dir(tmp_path) -> Path:
    """Temporary cache directory."""
    return tmp_path / "cache"


@pytest.fixture
def sample_grades() -> list[dict]:
    """Sample grade dicts for analysis testing."""
    grades = []
    for i in range(30):
        modality = ["xray", "ct", "mri", "ultrasound"][i % 4]
        anatomy = ["chest", "head", "abdomen", "knee"][i % 4]
        passed = i % 3 != 0  # 2/3 pass rate
        failure_class = None if passed else ["A", "B", "C", "D"][i % 4]
        grades.append(
            {
                "task_id": f"{modality.upper()}-{i:03d}",
                "model": "test-model",
                "trial": i % 3,
                "passed": passed,
                "weighted_score": 0.75 if passed else 0.3,
                "dimension_scores": {
                    "diagnostic_accuracy": 0.9 if passed else 0.2,
                    "finding_detection": 0.8 if passed else 0.3,
                    "anatomic_precision": 0.85 if passed else 0.4,
                    "clinical_relevance": 0.7 if passed else 0.3,
                    "false_positive_control": 0.95 if passed else 0.5,
                },
                "failure_class": failure_class,
                "detection_layer": 0,
                "metadata": {"modality": modality, "anatomy": anatomy},
            }
        )
    return grades
