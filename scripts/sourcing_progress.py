#!/usr/bin/env python3
"""Sourcing progress report: cross-references image_sources.yaml with task YAMLs.

Outputs coverage by modality and validation status.

Usage:
    python scripts/sourcing_progress.py
    python scripts/sourcing_progress.py --format json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml


def load_image_sources(path: str | Path = "corpus/image_sources.yaml") -> dict:
    path = Path(path)
    if not path.exists():
        return {"images": {}, "metadata": {}}
    with open(path) as f:
        return yaml.safe_load(f) or {"images": {}, "metadata": {}}


def load_all_tasks(tasks_dir: str | Path = "configs/tasks") -> list[dict]:
    tasks_dir = Path(tasks_dir)
    tasks = []
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if raw and "id" in raw:
            tasks.append(raw)
    return tasks


def compute_progress(
    sources_path: str = "corpus/image_sources.yaml",
    tasks_dir: str = "configs/tasks",
    images_dir: str = "corpus/images",
) -> dict:
    sources = load_image_sources(sources_path)
    images = sources.get("images", {})
    tasks = load_all_tasks(tasks_dir)

    # Build image_ref -> source entry lookup
    source_by_ref: dict[str, dict] = {}
    for ref, info in images.items():
        source_by_ref[ref] = info

    # Count tasks per modality and track which have sourced images
    by_modality: dict[str, dict] = defaultdict(lambda: {"total": 0, "sourced": 0, "validated": 0})
    status_counts: Counter = Counter()
    images_dir_path = Path(images_dir)

    # Track unique image_refs that are sourced/downloaded
    sourced_refs: set[str] = set()
    for ref, info in images.items():
        status = info.get("validation_status", "unsourced")
        if status in ("downloaded", "validated", "sourced"):
            sourced_refs.add(ref)

    for task in tasks:
        modality = task.get("modality", "unknown")
        image_ref = task.get("image_ref", "")
        by_modality[modality]["total"] += 1

        # Check if image is sourced (in image_sources with status != unsourced, or file exists)
        has_source = image_ref in source_by_ref and source_by_ref[image_ref].get(
            "validation_status", "unsourced"
        ) != "unsourced"
        has_file = (images_dir_path / image_ref).exists() if image_ref else False

        if has_source or has_file:
            by_modality[modality]["sourced"] += 1

        # Check if validated
        if image_ref in source_by_ref and source_by_ref[image_ref].get("pathology_confirmed"):
            by_modality[modality]["validated"] += 1

    # Overall validation_status counts from image_sources
    for ref, info in images.items():
        status_counts[info.get("validation_status", "unsourced")] += 1

    total_tasks = sum(m["total"] for m in by_modality.values())
    total_sourced = sum(m["sourced"] for m in by_modality.values())
    total_validated = sum(m["validated"] for m in by_modality.values())

    return {
        "total_tasks": total_tasks,
        "total_sourced": total_sourced,
        "total_validated": total_validated,
        "by_modality": dict(by_modality),
        "by_status": dict(status_counts),
        "total_image_entries": len(images),
    }


def format_text(progress: dict) -> str:
    lines = []
    total = progress["total_tasks"]
    sourced = progress["total_sourced"]
    validated = progress["total_validated"]
    pct = sourced / total * 100 if total else 0

    lines.append(f"Sourcing Progress: {sourced}/{total} ({pct:.1f}%)")
    lines.append(f"  Validated:       {validated}/{total}")
    lines.append("")

    # Per-modality
    for mod in sorted(progress["by_modality"].keys()):
        m = progress["by_modality"][mod]
        mod_pct = m["sourced"] / m["total"] * 100 if m["total"] else 0
        lines.append(f"  {mod:14s} {m['sourced']:>3d}/{m['total']:<3d} ({mod_pct:5.1f}%)")

    # Status counts
    lines.append("")
    lines.append("By validation_status:")
    for status, count in sorted(progress["by_status"].items()):
        lines.append(f"  {status}: {count}")

    lines.append(f"\nTotal image_sources entries: {progress['total_image_entries']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RadSlice sourcing progress report")
    parser.add_argument(
        "--sources", default="corpus/image_sources.yaml", help="Image sources YAML"
    )
    parser.add_argument("--tasks-dir", default="configs/tasks", help="Tasks directory")
    parser.add_argument("--images-dir", default="corpus/images", help="Images directory")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    args = parser.parse_args()

    progress = compute_progress(args.sources, args.tasks_dir, args.images_dir)

    if args.format == "json":
        print(json.dumps(progress, indent=2))
    else:
        print(format_text(progress))


if __name__ == "__main__":
    main()
