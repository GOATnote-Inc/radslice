"""Tests for executor.py — matrix execution."""

from __future__ import annotations

import json

import pytest
import yaml

from radslice.executor import MatrixConfig, MatrixExecutor, RunResult, _build_prompt
from radslice.grading.grader import RubricGrader
from radslice.providers.base import Provider, ProviderResponse
from radslice.task import GroundTruth, Task


class MockExecProvider(Provider):
    """Mock provider that returns configurable responses."""

    def __init__(self, response_text: str = "Normal chest x-ray."):
        self._response_text = response_text

    @property
    def name(self):
        return "mock"

    async def complete(
        self, messages, model, images=None, temperature=0.0, seed=42, max_tokens=4096
    ):
        return ProviderResponse(
            text=self._response_text,
            model=model,
            latency_ms=50.0,
        )


class TestMatrixConfig:
    def test_from_yaml(self, tmp_path):
        config = {
            "tasks_dir": "configs/tasks",
            "models": [{"name": "test", "provider": "openai", "model_id": "gpt-test"}],
            "n_trials": 2,
            "max_concurrency": 3,
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(config, f)

        mc = MatrixConfig.from_yaml(path)
        assert mc.tasks_dir == "configs/tasks"
        assert len(mc.models) == 1
        assert mc.n_trials == 2
        assert mc.max_concurrency == 3

    def test_defaults(self):
        mc = MatrixConfig(
            tasks_dir="tasks",
            models=[{"name": "m", "provider": "p", "model_id": "id"}],
        )
        assert mc.n_trials == 3
        assert mc.max_concurrency == 5
        assert mc.modality_filter is None
        assert mc.task_ids is None


class TestBuildPrompt:
    def test_diagnosis_prompt(self):
        task = Task(
            id="T",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="diagnosis",
            difficulty="basic",
            image_ref="t.png",
            prompt_template="diagnosis",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        prompt = _build_prompt(task)
        assert "expert radiologist" in prompt.lower()
        assert "diagnosis" in prompt.lower()

    def test_finding_detection_prompt(self):
        task = Task(
            id="T",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="finding_detection",
            difficulty="basic",
            image_ref="t.png",
            prompt_template="finding_detection",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        prompt = _build_prompt(task)
        assert "finding" in prompt.lower()

    def test_report_generation_prompt(self):
        task = Task(
            id="T",
            name="test",
            modality="xray",
            anatomy="chest",
            task_type="report_generation",
            difficulty="basic",
            image_ref="t.png",
            prompt_template="report_generation",
            ground_truth=GroundTruth(primary_diagnosis="test"),
        )
        prompt = _build_prompt(task)
        assert "report" in prompt.lower()


class TestMatrixExecutor:
    @pytest.mark.asyncio
    async def test_basic_run(self, sample_tasks_dir, tmp_path):
        provider = MockExecProvider("Right lower lobe condition_0 identified. Right side.")
        grader = RubricGrader(pattern_only=True)
        output_dir = tmp_path / "results"

        executor = MatrixExecutor(
            providers={"mock": provider},
            grader=grader,
            corpus_dir=tmp_path / "corpus",
            output_dir=output_dir,
        )

        config = MatrixConfig(
            tasks_dir=str(sample_tasks_dir),
            models=[{"name": "test", "provider": "mock", "model_id": "mock-1"}],
            n_trials=1,
            max_concurrency=2,
        )

        result = await executor.run(config)
        assert isinstance(result, RunResult)
        assert len(result.grades) == 5
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_resume(self, sample_tasks_dir, tmp_path):
        provider = MockExecProvider("condition_0 right")
        grader = RubricGrader(pattern_only=True)
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True)

        # Write some existing grades
        grades_file = output_dir / "grades.jsonl"
        existing = {
            "task_id": "XRAY-T000",
            "model": "test",
            "trial": 0,
            "passed": True,
            "weighted_score": 0.8,
            "dimension_scores": {},
            "failure_class": None,
            "detection_layer": 0,
        }
        with open(grades_file, "w") as f:
            f.write(json.dumps(existing) + "\n")

        executor = MatrixExecutor(
            providers={"mock": provider},
            grader=grader,
            corpus_dir=tmp_path / "corpus",
            output_dir=output_dir,
            resume=True,
        )

        config = MatrixConfig(
            tasks_dir=str(sample_tasks_dir),
            models=[{"name": "test", "provider": "mock", "model_id": "mock-1"}],
            n_trials=1,
        )

        result = await executor.run(config)
        # Should skip XRAY-T000:test:0
        assert len(result.grades) == 4

    @pytest.mark.asyncio
    async def test_modality_filter(self, sample_tasks_dir, tmp_path):
        provider = MockExecProvider("test")
        grader = RubricGrader(pattern_only=True)

        executor = MatrixExecutor(
            providers={"mock": provider},
            grader=grader,
            output_dir=tmp_path / "results",
        )

        config = MatrixConfig(
            tasks_dir=str(sample_tasks_dir),
            models=[{"name": "test", "provider": "mock", "model_id": "m"}],
            n_trials=1,
            modality_filter="ct",  # No CT tasks in fixture
        )

        result = await executor.run(config)
        assert len(result.grades) == 0

    @pytest.mark.asyncio
    async def test_task_id_filter(self, sample_tasks_dir, tmp_path):
        provider = MockExecProvider("condition_0 right")
        grader = RubricGrader(pattern_only=True)

        executor = MatrixExecutor(
            providers={"mock": provider},
            grader=grader,
            output_dir=tmp_path / "results",
        )

        config = MatrixConfig(
            tasks_dir=str(sample_tasks_dir),
            models=[{"name": "test", "provider": "mock", "model_id": "m"}],
            n_trials=1,
            task_ids=["XRAY-T000", "XRAY-T001"],
        )

        result = await executor.run(config)
        assert len(result.grades) == 2


class TestRunResult:
    def test_to_jsonl(self, tmp_path):
        from radslice.grading.grader import GradeResult

        result = RunResult()
        result.grades.append(
            GradeResult(
                task_id="T",
                model="m",
                trial=0,
                passed=True,
                weighted_score=0.8,
                dimension_scores={},
                failure_class=None,
                detection_layer=0,
            )
        )
        path = tmp_path / "grades.jsonl"
        result.to_jsonl(path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["task_id"] == "T"
