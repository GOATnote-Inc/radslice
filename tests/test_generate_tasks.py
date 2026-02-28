"""Tests for task generation script."""

import sys
from pathlib import Path

import pytest
import yaml

# Ensure scripts/ imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from generate_tasks import (
    VARIATION_DIMENSIONS,
    generate_variant,
    generate_variants,
)

from radslice.canary import RADSLICE_CANARY_GUID


@pytest.fixture
def source_task(tmp_path):
    """Create a minimal source task YAML."""
    task = {
        "id": "XRAY-001",
        "name": "Acute Heart Failure on Chest X-ray",
        "modality": "xray",
        "anatomy": "chest",
        "task_type": "diagnosis",
        "difficulty": "intermediate",
        "image_ref": "xray/openem/acute-heart-failure.png",
        "condition_id": "acute-heart-failure",
        "lostbench_scenario_id": "",
        "ground_truth": {
            "primary_diagnosis": "Acute decompensated heart failure",
            "differential": ["Bilateral pneumonia", "ARDS"],
            "key_findings": [
                {"finding": "Cardiomegaly", "location": "cardiac silhouette", "required": True},
            ],
            "severity": "severe",
            "laterality": "bilateral",
            "negatives": [],
        },
        "pattern_checks": [
            {
                "name": "diagnosis",
                "check_type": "regex",
                "pattern": "(?i)heart failure",
                "required": True,
            },
        ],
        "reference_solution": "Acute heart failure with cardiomegaly.",
        "condition_present": True,
        "tags": ["cardiac", "emergency"],
        "metadata": {},
    }
    path = tmp_path / "XRAY-001.yaml"
    with open(path, "w") as f:
        yaml.dump(task, f)
    return path


class TestGenerateVariant:
    """Test single variant generation."""

    def test_new_id_format(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["id"].startswith("XRAY-G")
        assert variant["id"] != source["id"]

    def test_difficulty_escalation(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        # intermediate -> advanced
        assert variant["difficulty"] == "advanced"

    def test_difficulty_cap_at_expert(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        source["difficulty"] = "expert"
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["difficulty"] == "expert"

    def test_multi_system_escalates_two_levels(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        # intermediate -> expert (2 levels)
        variant = generate_variant(source, "multi_system_pathology", 0, tmp_path)
        assert variant["difficulty"] == "expert"

    def test_variation_metadata(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "sparse_clinical_history", 0, tmp_path)
        assert variant["metadata"]["parent_task_id"] == "XRAY-001"
        assert variant["metadata"]["variation_dimension"] == "sparse_clinical_history"
        assert variant["metadata"]["generated"] is True

    def test_canary_embedded(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "laterality_traps", 0, tmp_path)
        assert variant["metadata"]["_canary"] == RADSLICE_CANARY_GUID

    def test_tags_include_generated(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "incidental_findings", 0, tmp_path)
        assert "generated" in variant["tags"]
        assert "incidental_findings" in variant["tags"]
        # Original tags preserved
        assert "cardiac" in variant["tags"]

    def test_ground_truth_preserved(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        src_diag = source["ground_truth"]["primary_diagnosis"]
        assert variant["ground_truth"]["primary_diagnosis"] == src_diag
        assert variant["condition_id"] == source["condition_id"]

    def test_condition_id_preserved(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "image_quality_degradation", 0, tmp_path)
        assert variant["condition_id"] == "acute-heart-failure"


class TestGenerateVariants:
    """Test batch variant generation."""

    def test_generates_n_variants(self, source_task, tmp_path):
        output_dir = tmp_path / "output"
        variants = generate_variants(
            source_task,
            "differential_complexity",
            output_dir,
            n_variants=3,
        )
        assert len(variants) == 3

    def test_unique_ids(self, source_task, tmp_path):
        output_dir = tmp_path / "output"
        variants = generate_variants(
            source_task,
            "differential_complexity",
            output_dir,
            n_variants=5,
        )
        ids = [v["id"] for v in variants]
        assert len(set(ids)) == 5

    def test_dry_run_no_files(self, source_task, tmp_path):
        output_dir = tmp_path / "dry_output"
        variants = generate_variants(
            source_task, "differential_complexity", output_dir, n_variants=2, dry_run=True
        )
        assert len(variants) == 2
        # No files written
        assert not output_dir.exists() or len(list(output_dir.glob("*.yaml"))) == 0

    def test_writes_files(self, source_task, tmp_path):
        output_dir = tmp_path / "output"
        generate_variants(
            source_task,
            "sparse_clinical_history",
            output_dir,
            n_variants=2,
        )
        yamls = list(output_dir.glob("*.yaml"))
        assert len(yamls) == 2

    def test_written_yaml_valid(self, source_task, tmp_path):
        output_dir = tmp_path / "output"
        generate_variants(source_task, "laterality_traps", output_dir, n_variants=1)
        yamls = list(output_dir.glob("*.yaml"))
        assert len(yamls) == 1
        with open(yamls[0]) as f:
            data = yaml.safe_load(f)
        assert "id" in data
        assert "metadata" in data
        assert data["metadata"]["generated"] is True

    def test_invalid_variation_raises(self, source_task, tmp_path):
        with pytest.raises(ValueError, match="Unknown variation"):
            generate_variants(source_task, "nonexistent_variation", tmp_path)

    def test_all_variations_valid(self, source_task, tmp_path):
        """All 6 variation dimensions produce valid variants."""
        for variation in VARIATION_DIMENSIONS:
            output_dir = tmp_path / variation
            variants = generate_variants(
                source_task, variation, output_dir, n_variants=1, dry_run=True
            )
            assert len(variants) == 1
            assert variants[0]["metadata"]["variation_dimension"] == variation


class TestIDConvention:
    """Test generated task ID conventions."""

    def test_xray_prefix(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["id"].startswith("XRAY-G")

    def test_ct_prefix(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        source["modality"] = "ct"
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["id"].startswith("CT-G")

    def test_mri_prefix(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        source["modality"] = "mri"
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["id"].startswith("MRI-G")

    def test_ultrasound_prefix(self, source_task, tmp_path):
        with open(source_task) as f:
            source = yaml.safe_load(f)
        source["modality"] = "ultrasound"
        variant = generate_variant(source, "differential_complexity", 0, tmp_path)
        assert variant["id"].startswith("US-G")
