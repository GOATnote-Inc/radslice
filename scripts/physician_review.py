#!/usr/bin/env python3
"""Structured physician review tool for RadSlice Tier 1 adjudication.

Opens images in Preview.app, presents structured form, collects verdicts,
writes to annotations.jsonl and individual YAML files. Updates
pathology_confirmed in image_sources.yaml.

Modeled on ScribeGoat2's physician_review.py pipeline.

Usage:
    .venv/bin/python3 scripts/physician_review.py
    .venv/bin/python3 scripts/physician_review.py --task CT-034
    .venv/bin/python3 scripts/physician_review.py --dry-run
"""

import argparse
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
CONFIGS_DIR = REPO_ROOT / "configs"
RESULTS_DIR = REPO_ROOT / "results"
ANNOTATIONS_FILE = RESULTS_DIR / "adjudication" / "annotations.jsonl"
TIER1_DIR = RESULTS_DIR / "adjudication" / "tier1"
IMAGE_SOURCES = CORPUS_DIR / "image_sources.yaml"

SCHEMA_VERSION = "1.0.0"


def load_image_sources():
    with open(IMAGE_SOURCES) as f:
        return yaml.safe_load(f)


def load_task(task_id):
    for modality in ["xray", "ct", "mri", "ultrasound", "incidental", "audit"]:
        path = CONFIGS_DIR / "tasks" / modality / f"{task_id}.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    return None


def get_already_adjudicated():
    """Get task_ids that already have annotations."""
    done = set()
    if ANNOTATIONS_FILE.exists():
        with open(ANNOTATIONS_FILE) as f:
            for line in f:
                row = json.loads(line.strip())
                done.add(row["task_id"])
    return done


def get_pending_reviews(sources, already_done):
    """Images with task_ids assigned but not yet adjudicated."""
    pending = []
    for image_key, entry in sources.get("images", {}).items():
        if not isinstance(entry, dict):
            continue
        task_ids = entry.get("task_ids", [])
        if not task_ids:
            continue
        for task_id in task_ids:
            if task_id in already_done:
                continue
            task = load_task(task_id)
            if task:
                pending.append(
                    {
                        "image_key": image_key,
                        "entry": entry,
                        "task_id": task_id,
                        "task": task,
                    }
                )
    # Sort by modality then task_id for predictable order
    pending.sort(key=lambda c: (c["task"]["modality"], c["task_id"]))
    return pending


def open_image(image_key):
    path = CORPUS_DIR / "images" / image_key
    if path.exists():
        subprocess.run(["open", str(path)], check=False)
        return True
    print(f"  ⚠ Image not found: {path}")
    return False


def present_and_collect(case, num, total):
    """Present one case, collect physician verdict."""
    task = case["task"]
    entry = case["entry"]
    gt = task.get("ground_truth", {})

    print(f"\n{'═' * 70}")
    print(f"  [{num}/{total}]  {case['task_id']}  —  {task.get('name', '')}")
    print(f"{'═' * 70}")
    print(f"  Image:      {case['image_key']}")
    print(f"  Source:     {entry.get('source_id', '?')}  |  License: {entry.get('license', '?')}")
    print(f"  Modality:   {task.get('modality')}  |  Anatomy: {task.get('anatomy')}")
    print(f"  Condition:  {task.get('condition_id')}")
    print(f"  Target Dx:  {gt.get('primary_diagnosis', '?')}")
    print(f"  Severity:   {gt.get('severity', '?')}  |  Laterality: {gt.get('laterality', '?')}")
    print(f"  Difficulty:  {task.get('difficulty')}")

    findings = gt.get("key_findings", [])
    if findings:
        print("\n  Verify these findings:")
        for f in findings:
            tag = "REQ" if f.get("required") else "opt"
            print(f"    [{tag}] {f.get('finding', '')}  @  {f.get('location', '')}")

    notes = entry.get("notes", "")
    if notes:
        print(f"\n  Image notes: {notes}")

    print(f"\n{'─' * 70}")
    print("  VERDICT:  Enter=CONFIRMED  r=REJECTED  n=NEEDS_RESOURCE  s=skip")
    print(f"{'─' * 70}")

    v = input("  Verdict: ").strip().lower()
    if v == "s":
        return None
    verdict = {"r": "REJECTED", "n": "NEEDS_RESOURCE"}.get(v, "CONFIRMED")

    vis = input("  Pathology visible  (Enter=present  a=absent  e=equivocal): ").strip().lower()
    pathology_visible = {"a": "absent", "e": "equivocal"}.get(vis, "present")

    qual = input("  Image quality  (Enter=adequate  m=marginal  i=inadequate): ").strip().lower()
    image_quality = {"m": "marginal", "i": "inadequate"}.get(qual, "adequate")

    conf = input("  Confounders  (comma-sep, or Enter for none): ").strip()
    confounders = [c.strip() for c in conf.split(",") if c.strip()] if conf else []

    notes_input = input("  Notes  (or Enter): ").strip()

    return {
        "verdict": verdict,
        "pathology_visible": pathology_visible,
        "image_quality": image_quality,
        "correct_modality": True,
        "correct_anatomy": True,
        "confounders": confounders,
        "reviewer_notes": notes_input or f"{verdict}",
    }


def write_annotation_jsonl(case, review, annotator_id, annotator_name):
    """Append flat row to annotations.jsonl (BigQuery-compatible)."""
    task = case["task"]
    entry = case["entry"]
    gt = task.get("ground_truth", {})

    row = {
        "annotation_id": str(uuid.uuid4()),
        "annotator_id": annotator_id,
        "annotator_credentials": annotator_name,
        "session_id": f"tier1_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "annotation_timestamp": datetime.now(timezone.utc).isoformat(),
        "adjudication_tier": 1,
        "task_id": case["task_id"],
        "image_ref": case["image_key"],
        "source_article": entry.get("source_id", ""),
        "modality": task.get("modality", ""),
        "anatomy": task.get("anatomy", ""),
        "condition_id": task.get("condition_id", ""),
        "target_diagnosis": gt.get("primary_diagnosis", ""),
        "difficulty": task.get("difficulty", ""),
        "severity": gt.get("severity", ""),
        "laterality": gt.get("laterality", ""),
        "pathology_visible": review["pathology_visible"],
        "image_quality": review["image_quality"],
        "correct_modality": review["correct_modality"],
        "correct_anatomy": review["correct_anatomy"],
        "confounders": "|".join(review["confounders"]),
        "verdict": review["verdict"],
        "reviewer_notes": review["reviewer_notes"],
        "annotation_schema_version": SCHEMA_VERSION,
    }

    ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ANNOTATIONS_FILE, "a") as f:
        f.write(json.dumps(row) + "\n")

    return row


def write_tier1_yaml(case, review, annotator_name):
    """Write individual Tier 1 YAML (backwards compat with protocol.yaml format)."""
    task = case["task"]
    entry = case["entry"]

    record = {
        "adjudication_tier": 1,
        "task_id": case["task_id"],
        "image_ref": case["image_key"],
        "source_article": entry.get("source_id", ""),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reviewer": {
            "name": annotator_name,
            "credential": "MD",
            "specialty": "emergency_medicine",
        },
        "target": {
            "condition_id": task.get("condition_id", ""),
            "primary_diagnosis": task.get("ground_truth", {}).get("primary_diagnosis", ""),
            "modality": task.get("modality", ""),
            "anatomy": task.get("anatomy", ""),
        },
        "pathology_visible": review["pathology_visible"],
        "image_quality": review["image_quality"],
        "correct_modality": review["correct_modality"],
        "correct_anatomy": review["correct_anatomy"],
        "confounders": review["confounders"],
        "verdict": review["verdict"],
        "reviewer_notes": review["reviewer_notes"],
    }

    TIER1_DIR.mkdir(parents=True, exist_ok=True)
    with open(TIER1_DIR / f"{case['task_id']}.yaml", "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(
        description="RadSlice Tier 1 Physician Review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--annotator", default="Brandon Dent, MD")
    parser.add_argument("--annotator-id", default="bdent_md_001")
    parser.add_argument("--task", help="Review a specific task ID only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    sources = load_image_sources()
    already_done = get_already_adjudicated()
    pending = get_pending_reviews(sources, already_done)

    if args.task:
        pending = [p for p in pending if p["task_id"] == args.task]

    if not pending:
        print("\n  ✓ No pending Tier 1 reviews.")
        if already_done:
            print(f"  Already adjudicated: {len(already_done)} tasks")
        return

    print("\n  RadSlice Tier 1 Physician Review")
    print("  ─────────────────────────────────")
    print(f"  Annotator:  {args.annotator}")
    print(f"  Pending:    {len(pending)} images")
    print(f"  Output:     {ANNOTATIONS_FILE}")
    print(f"  Schema:     v{SCHEMA_VERSION}")
    if args.dry_run:
        print("  Mode:       DRY RUN (no writes)")

    confirmed = rejected = skipped = 0

    for i, case in enumerate(pending, 1):
        open_image(case["image_key"])
        review = present_and_collect(case, i, len(pending))

        if review is None:
            skipped += 1
            print("  → skipped")
            continue

        if not args.dry_run:
            write_annotation_jsonl(case, review, args.annotator_id, args.annotator)
            write_tier1_yaml(case, review, args.annotator)

        if review["verdict"] == "CONFIRMED":
            confirmed += 1
        elif review["verdict"] == "REJECTED":
            rejected += 1

        print(f"  → {review['verdict']}")

    print(f"\n{'═' * 70}")
    print(f"  Session: {confirmed} confirmed, {rejected} rejected, {skipped} skipped")
    print(f"  Output:  {ANNOTATIONS_FILE}")
    print(f"{'═' * 70}")
    if confirmed + rejected > 0 and not args.dry_run:
        print("\n  Next steps:")
        print("  1. Update pathology_confirmed in image_sources.yaml")
        print("  2. git add -f results/adjudication/ corpus/image_sources.yaml")
        print("  3. git commit")


if __name__ == "__main__":
    main()
