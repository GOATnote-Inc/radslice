"""Smoke tests — end-to-end pipeline with mock executor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from radslice.analysis.per_modality import modality_breakdown
from radslice.analysis.report import format_report
from radslice.executor import MatrixConfig, MatrixExecutor
from radslice.grading.grader import RubricGrader
from radslice.providers.base import Provider, ProviderResponse
from radslice.scoring import (
    compute_pass_at_k_rate,
    compute_pass_pow_k_rate,
    wilson_ci,
)


class SmokeMockProvider(Provider):
    """Mock provider that returns radiology-like responses."""

    RESPONSES = {
        "XRAY": "Left pneumothorax identified. Visceral pleural line visible in the left hemithorax. No mediastinal shift. Simple pneumothorax without tension.",
        "CT": "Acute subdural hematoma identified. Crescent-shaped hyperdense collection. Midline shift present.",
        "MRI": "ACL tear confirmed. T2 hyperintense signal discontinuity of the anterior cruciate ligament. Left knee.",
        "US": "Gallstones identified. Hyperechoic foci with posterior acoustic shadowing in the gallbladder.",
    }

    @property
    def name(self):
        return "smoke-mock"

    async def complete(
        self, messages, model, images=None, temperature=0.0, seed=42, max_tokens=4096
    ):
        # Return modality-appropriate response based on content hints
        text = str(messages)
        for prefix, response in self.RESPONSES.items():
            if prefix.lower() in text.lower():
                return ProviderResponse(text=response, model=model, latency_ms=10.0)
        return ProviderResponse(
            text="Normal study. No acute findings.", model=model, latency_ms=10.0
        )


@pytest.mark.smoke
class TestSmokeEndToEnd:
    """End-to-end smoke tests using mock provider."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, sample_tasks_dir, tmp_path):
        """Run full pipeline: load tasks → execute → grade → analyze."""
        provider = SmokeMockProvider()
        grader = RubricGrader(pattern_only=True)
        output_dir = tmp_path / "smoke_results"

        executor = MatrixExecutor(
            providers={"smoke-mock": provider},
            grader=grader,
            output_dir=output_dir,
        )

        config = MatrixConfig(
            tasks_dir=str(sample_tasks_dir),
            models=[{"name": "smoke-test", "provider": "smoke-mock", "model_id": "mock-v1"}],
            n_trials=2,
            max_concurrency=3,
        )

        result = await executor.run(config)

        # Verify execution
        assert len(result.grades) == 10  # 5 tasks × 2 trials
        assert len(result.errors) == 0

        # Verify grades file written
        grades_file = output_dir / "grades.jsonl"
        assert grades_file.exists()
        with open(grades_file) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 10

        # Verify transcripts written
        transcript_file = output_dir / "transcripts.jsonl"
        assert transcript_file.exists()

    @pytest.mark.asyncio
    async def test_scoring_pipeline(self):
        """Test scoring computations end-to-end."""
        # Simulate trial results for 5 scenarios, 3 trials each
        scenario_trials = [
            [True, True, True],  # All pass
            [True, False, True],  # 2/3 pass
            [False, False, False],  # All fail
            [True, True, False],  # 2/3 pass
            [True, True, True],  # All pass
        ]

        pass_at_k = compute_pass_at_k_rate(scenario_trials)
        pass_pow_k = compute_pass_pow_k_rate(scenario_trials)

        assert pass_at_k == pytest.approx(4 / 5)  # 4 scenarios have at least 1 pass
        assert pass_pow_k == pytest.approx(2 / 5)  # 2 scenarios have all pass

        # Wilson CI on pass^k
        n_pass_pow_k = 2
        n_total = 5
        lo, hi = wilson_ci(n_pass_pow_k, n_total)
        assert 0.0 <= lo <= hi <= 1.0

    def test_analysis_pipeline(self, sample_grades):
        """Test analysis and reporting pipeline."""
        # Modality breakdown
        mod_results = modality_breakdown(sample_grades)
        assert len(mod_results) > 0

        # Format as markdown
        report_data = {
            "total_grades": len(sample_grades),
            "by_modality": mod_results,
        }
        md = format_report(report_data, "markdown")
        assert "RadSlice" in md
        assert "Per-Modality" in md

        # Format as JSON
        js = format_report(report_data, "json")
        parsed = json.loads(js)
        assert parsed["total_grades"] == 30


@pytest.mark.smoke
class TestSmokeTaskLoading:
    """Smoke test loading actual task YAMLs from configs."""

    def test_load_real_xray_tasks(self):
        """Load real X-ray task YAMLs if they exist."""
        tasks_dir = Path("configs/tasks/xray")
        if not tasks_dir.exists():
            pytest.skip("Task YAMLs not available")

        from radslice.task import load_tasks_from_dir

        tasks = load_tasks_from_dir(tasks_dir)
        assert len(tasks) > 0
        for task in tasks:
            assert task.modality == "xray"
            assert task.ground_truth.primary_diagnosis

    def test_load_all_tasks(self):
        """Load all task YAMLs across modalities."""
        tasks_dir = Path("configs/tasks")
        if not tasks_dir.exists():
            pytest.skip("Task YAMLs not available")

        from radslice.task import load_tasks_by_modality

        grouped = load_tasks_by_modality(tasks_dir)
        for modality, tasks in grouped.items():
            assert modality in {"xray", "ct", "mri", "ultrasound"}
            assert len(tasks) > 0
