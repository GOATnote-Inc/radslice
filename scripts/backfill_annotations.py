#!/usr/bin/env python3
"""One-time backfill: convert existing tier1 YAML adjudications to annotations.jsonl."""

import json
import uuid
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
TIER1_DIR = REPO_ROOT / "results" / "adjudication" / "tier1"
ANNOTATIONS_FILE = REPO_ROOT / "results" / "adjudication" / "annotations.jsonl"
IMAGE_SOURCES = REPO_ROOT / "corpus" / "image_sources.yaml"
CONFIGS_DIR = REPO_ROOT / "configs"

SCHEMA_VERSION = "1.0.0"
ANNOTATOR_ID = "bdent_md_001"
ANNOTATOR_NAME = "Brandon Dent, MD"


def load_task(task_id):
    for modality in ["xray", "ct", "mri", "ultrasound", "incidental", "audit"]:
        path = CONFIGS_DIR / "tasks" / modality / f"{task_id}.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    return None


def main():
    existing = set()
    if ANNOTATIONS_FILE.exists():
        with open(ANNOTATIONS_FILE) as f:
            for line in f:
                row = json.loads(line.strip())
                existing.add(row["task_id"])

    yamls = sorted(TIER1_DIR.glob("*.yaml"))
    written = 0

    for ypath in yamls:
        with open(ypath) as f:
            rec = yaml.safe_load(f)

        task_id = rec["task_id"]
        if task_id in existing:
            print(f"  skip {task_id} (already in annotations.jsonl)")
            continue

        task = load_task(task_id)
        if not task:
            print(f"  skip {task_id} (task YAML not found)")
            continue

        gt = task.get("ground_truth", {})

        # Find source entry
        source_id = rec.get("source_article", "")
        image_ref = rec.get("image_ref", "")

        row = {
            "annotation_id": str(uuid.uuid4()),
            "annotator_id": ANNOTATOR_ID,
            "annotator_credentials": ANNOTATOR_NAME,
            "session_id": f"tier1_{rec.get('date', '2026-03-07')}",
            "annotation_timestamp": f"{rec.get('date', '2026-03-07')}T00:00:00+00:00",
            "adjudication_tier": 1,
            "task_id": task_id,
            "image_ref": image_ref,
            "source_article": source_id,
            "modality": task.get("modality", ""),
            "anatomy": task.get("anatomy", ""),
            "condition_id": task.get("condition_id", ""),
            "target_diagnosis": gt.get("primary_diagnosis", ""),
            "difficulty": task.get("difficulty", ""),
            "severity": gt.get("severity", ""),
            "laterality": gt.get("laterality", ""),
            "pathology_visible": rec.get("pathology_visible", ""),
            "image_quality": rec.get("image_quality", ""),
            "correct_modality": rec.get("correct_modality", True),
            "correct_anatomy": rec.get("correct_anatomy", True),
            "confounders": "|".join(rec.get("confounders", [])),
            "verdict": rec.get("verdict", ""),
            "reviewer_notes": rec.get("reviewer_notes", "").strip(),
            "annotation_schema_version": SCHEMA_VERSION,
        }

        ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ANNOTATIONS_FILE, "a") as f:
            f.write(json.dumps(row) + "\n")

        written += 1
        print(f"  wrote {task_id}")

    print(f"\nBackfilled {written} annotations to {ANNOTATIONS_FILE}")


if __name__ == "__main__":
    main()
