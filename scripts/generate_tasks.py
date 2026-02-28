#!/usr/bin/env python3
"""Generate task variants for corpus evolution.

Takes a source task YAML and produces harder variants along specified
variation dimensions. Generated task IDs use G-prefix: {MODALITY}-G{NNN}.

Usage:
    python scripts/generate_tasks.py --source-task configs/tasks/xray/XRAY-001.yaml \
        --variation differential_complexity --output-dir configs/tasks/xray/ \
        --n-variants 3 --dry-run
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.canary import embed_canary_in_json

# Radiology-specific variation dimensions
VARIATION_DIMENSIONS = {
    "image_quality_degradation": {
        "description": "Suboptimal positioning, motion artifact, low contrast",
        "difficulty_modifier": 1,
        "prompt_modifier": "The image is of suboptimal quality with {artifact_type}. ",
        "artifacts": [
            "motion artifact",
            "poor positioning",
            "low contrast",
            "suboptimal exposure",
            "overlapping structures",
        ],
    },
    "sparse_clinical_history": {
        "description": "Minimal or misleading clinical context",
        "difficulty_modifier": 1,
        "prompt_modifier": "Limited clinical history: {sparse_history}. ",
        "histories": [
            "chest pain",
            "shortness of breath",
            "abdominal pain",
            "fall",
            "routine screening",
        ],
    },
    "differential_complexity": {
        "description": "More confounders, rarer differentials",
        "difficulty_modifier": 1,
        "prompt_modifier": "",
    },
    "incidental_findings": {
        "description": "Important incidental findings alongside primary pathology",
        "difficulty_modifier": 1,
        "prompt_modifier": "",
    },
    "laterality_traps": {
        "description": "Bilateral vs unilateral confusion, mirror-image anatomy",
        "difficulty_modifier": 1,
        "prompt_modifier": "",
    },
    "multi_system_pathology": {
        "description": "Multiple concurrent pathologies across organ systems",
        "difficulty_modifier": 2,
        "prompt_modifier": "",
    },
}

DIFFICULTY_LEVELS = ["basic", "intermediate", "advanced", "expert"]

MODALITY_PREFIXES = {
    "xray": "XRAY",
    "ct": "CT",
    "mri": "MRI",
    "ultrasound": "US",
}


def _escalate_difficulty(current: str) -> str:
    """Escalate difficulty by one level (capped at expert)."""
    idx = DIFFICULTY_LEVELS.index(current) if current in DIFFICULTY_LEVELS else 1
    new_idx = min(idx + 1, len(DIFFICULTY_LEVELS) - 1)
    return DIFFICULTY_LEVELS[new_idx]


def _next_generated_id(modality: str, output_dir: Path) -> str:
    """Compute next generated task ID: {PREFIX}-G{NNN}."""
    prefix = MODALITY_PREFIXES.get(modality, modality.upper())
    existing = []
    if output_dir.exists():
        for f in output_dir.glob("*.yaml"):
            name = f.stem
            if "-G" in name:
                try:
                    num = int(name.split("-G")[-1])
                    existing.append(num)
                except ValueError:
                    pass
    next_num = max(existing, default=0) + 1
    return f"{prefix}-G{next_num:03d}"


def generate_variant(
    source: dict,
    variation: str,
    variant_idx: int,
    output_dir: Path,
) -> dict:
    """Generate a single task variant from a source task.

    Args:
        source: Source task YAML data.
        variation: Variation dimension name.
        variant_idx: Index within this batch (for unique IDs).
        output_dir: Directory to check for existing generated IDs.

    Returns:
        New task dict with escalated difficulty and variation metadata.
    """
    variant = copy.deepcopy(source)

    # Generate new ID
    modality = source.get("modality", "xray")
    new_id = _next_generated_id(modality, output_dir)
    # Adjust for batch offset
    prefix = MODALITY_PREFIXES.get(modality, modality.upper())
    existing = []
    if output_dir.exists():
        for f in output_dir.glob("*.yaml"):
            name = f.stem
            if "-G" in name:
                try:
                    num = int(name.split("-G")[-1])
                    existing.append(num)
                except ValueError:
                    pass
    next_num = max(existing, default=0) + 1 + variant_idx
    new_id = f"{prefix}-G{next_num:03d}"

    variant["id"] = new_id

    # Escalate difficulty
    current_difficulty = source.get("difficulty", "intermediate")
    dim = VARIATION_DIMENSIONS.get(variation, {})
    modifier = dim.get("difficulty_modifier", 1)
    new_difficulty = current_difficulty
    for _ in range(modifier):
        new_difficulty = _escalate_difficulty(new_difficulty)
    variant["difficulty"] = new_difficulty

    # Update name to reflect variation
    variant["name"] = f"{source.get('name', 'Task')} ({variation.replace('_', ' ')})"

    # Add variation metadata
    metadata = dict(variant.get("metadata", {}))
    metadata["parent_task_id"] = source.get("id", "unknown")
    metadata["variation_dimension"] = variation
    metadata["variation_description"] = dim.get("description", "")
    metadata["generated"] = True
    variant["metadata"] = metadata

    # Embed canary
    variant = embed_canary_in_json(variant)

    # Update tags
    tags = list(variant.get("tags", []))
    if "generated" not in tags:
        tags.append("generated")
    if variation not in tags:
        tags.append(variation)
    variant["tags"] = tags

    return variant


def generate_variants(
    source_path: str | Path,
    variation: str,
    output_dir: str | Path,
    n_variants: int = 3,
    dry_run: bool = False,
) -> list[dict]:
    """Generate multiple task variants from a source task.

    Args:
        source_path: Path to source task YAML.
        variation: Variation dimension name.
        output_dir: Directory to write variants.
        n_variants: Number of variants to generate.
        dry_run: If True, don't write files.

    Returns:
        List of generated variant dicts.
    """
    source_path = Path(source_path)
    output_dir = Path(output_dir)

    if variation not in VARIATION_DIMENSIONS:
        raise ValueError(
            f"Unknown variation: {variation}. Valid: {list(VARIATION_DIMENSIONS.keys())}"
        )

    with open(source_path) as f:
        source = yaml.safe_load(f)

    variants = []
    for i in range(n_variants):
        variant = generate_variant(source, variation, i, output_dir)
        variants.append(variant)

        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{variant['id']}.yaml"
            with open(out_path, "w") as f:
                yaml.dump(variant, f, default_flow_style=False, sort_keys=False)
            print(f"  Written: {out_path}")

    return variants


def main():
    parser = argparse.ArgumentParser(description="Generate task variants for corpus evolution")
    parser.add_argument(
        "--source-task",
        required=True,
        help="Path to source task YAML",
    )
    parser.add_argument(
        "--variation",
        required=True,
        choices=list(VARIATION_DIMENSIONS.keys()),
        help="Variation dimension",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for generated tasks",
    )
    parser.add_argument(
        "--n-variants",
        type=int,
        default=3,
        help="Number of variants to generate (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated tasks without writing files",
    )

    args = parser.parse_args()

    print(f"Source: {args.source_task}")
    print(f"Variation: {args.variation}")
    print(f"Output: {args.output_dir}")
    print(f"Variants: {args.n_variants}")
    print(f"Dry run: {args.dry_run}")
    print()

    variants = generate_variants(
        source_path=args.source_task,
        variation=args.variation,
        output_dir=args.output_dir,
        n_variants=args.n_variants,
        dry_run=args.dry_run,
    )

    print(f"\nGenerated {len(variants)} variants:")
    for v in variants:
        print(f"  {v['id']}: {v['name']} (difficulty={v['difficulty']})")
        if args.dry_run:
            print(f"    metadata: {json.dumps(v.get('metadata', {}), indent=2)}")


if __name__ == "__main__":
    main()
