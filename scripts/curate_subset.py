"""Build a balanced evaluation subset from the full task corpus."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from radslice.task import load_tasks_from_dir


def curate_subset(
    tasks_dir: str,
    target_per_modality: dict[str, int] | None = None,
    seed: int = 42,
) -> dict[str, list]:
    """Select a balanced subset of tasks.

    Ensures each modality has positive, normal, and confusion-pair cases.
    """
    if target_per_modality is None:
        target_per_modality = {"xray": 20, "ct": 15, "mri": 10, "ultrasound": 5}

    rng = random.Random(seed)
    all_tasks = load_tasks_from_dir(tasks_dir)

    by_modality: dict[str, list] = {}
    for task in all_tasks:
        by_modality.setdefault(task.modality, []).append(task)

    selected: dict[str, list] = {}
    for modality, target_n in target_per_modality.items():
        pool = by_modality.get(modality, [])
        if not pool:
            continue

        # Stratify: positive, normal, confusion-pair
        positives = [t for t in pool if t.condition_present and not t.confusion_pair]
        normals = [t for t in pool if not t.condition_present]
        confusion = [t for t in pool if t.confusion_pair]

        rng.shuffle(positives)
        rng.shuffle(normals)
        rng.shuffle(confusion)

        # Allocate: ~60% positive, ~20% normal, ~20% confusion
        n_pos = max(1, int(target_n * 0.6))
        n_norm = max(1, int(target_n * 0.2))
        n_conf = target_n - n_pos - n_norm

        subset = (
            positives[:n_pos]
            + normals[:n_norm]
            + confusion[:n_conf]
        )
        selected[modality] = subset[:target_n]

    return selected


def main():
    parser = argparse.ArgumentParser(description="Curate balanced evaluation subset")
    parser.add_argument("--tasks-dir", default="configs/tasks")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="-", help="Output file (- for stdout)")
    args = parser.parse_args()

    subset = curate_subset(args.tasks_dir, seed=args.seed)

    for modality, tasks in sorted(subset.items()):
        print(f"\n{modality.upper()} ({len(tasks)} tasks):")
        for task in tasks:
            flags = []
            if not task.condition_present:
                flags.append("NORMAL")
            if task.confusion_pair:
                flags.append(f"CONFUSION→{task.confusion_pair}")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {task.id}: {task.name}{flag_str}")


if __name__ == "__main__":
    main()
