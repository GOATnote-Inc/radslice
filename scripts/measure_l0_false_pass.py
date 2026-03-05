#!/usr/bin/env python3
"""Measure L0 false-pass reduction from context-aware pattern matching.

Replays all stored transcripts through the updated patterns.py and compares
old vs new L0 pass/fail against the L2 judge verdicts from regrade results.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.grading.patterns import (
    extract_diagnostic_sections,
    run_task_patterns,
)
from radslice.task import load_tasks_from_dir


def main():
    tasks = {t.id: t for t in load_tasks_from_dir("configs/tasks")}

    # Load L2 judge verdicts from regrades
    l2_verdicts = {}

    # Opus L0-only regrade (judged by GPT-5.2)
    with open("results/calibration-regrade-l0only-20260305.json") as f:
        opus_regrade = json.load(f)
    for g in opus_regrade["grades"]:
        key = f"{g['task_id']}:{g['trial']}:opus"
        l2_verdicts[key] = g["now_pass"]

    # GPT regrade (judged by Opus 4.6)
    with open("results/regrade-gpt52-rc10-20260306.json") as f:
        gpt_regrade = json.load(f)
    for g in gpt_regrade["grades"]:
        key = f"{g['task_id']}:{g['trial']}:gpt"
        l2_verdicts[key] = g["now_pass"]

    # Load original L0 grades
    orig_grades = {}
    for model_tag, grades_file in [
        ("opus", "results/eval-20260303-opus46-rc10/grades.jsonl"),
        ("gpt", "results/eval-20260303-gpt52-rc10/grades.jsonl"),
    ]:
        with open(grades_file) as f:
            for line in f:
                g = json.loads(line)
                key = f"{g['task_id']}:{g['trial']}:{model_tag}"
                orig_grades[key] = g

    # Load transcripts
    transcripts = {}
    for model_tag, trans_file in [
        ("opus", "results/eval-20260303-opus46-rc10/transcripts.jsonl"),
        ("gpt", "results/eval-20260303-gpt52-rc10/transcripts.jsonl"),
    ]:
        with open(trans_file) as f:
            for line in f:
                t = json.loads(line)
                if t.get("task_id") and t["task_id"] in tasks:
                    key = f"{t['task_id']}:{t['trial']}:{model_tag}"
                    transcripts[key] = t

    # Run comparison
    old_fp = 0  # L0 pass, L2 fail (false positives)
    new_fp = 0
    old_tp = 0  # L0 pass, L2 pass (true positives)
    new_tp = 0
    old_tn = 0  # L0 fail, L2 fail (true negatives)
    new_tn = 0
    old_fn = 0  # L0 fail, L2 pass (false negatives)
    new_fn = 0
    total = 0
    flipped_fp_to_tn = []  # Fixed false passes
    flipped_tp_to_fn = []  # Broken true passes
    section_detected = 0
    section_not_detected = 0

    for key, l2_pass in l2_verdicts.items():
        if key not in transcripts or key not in orig_grades:
            continue

        task_id = key.split(":")[0]
        task = tasks.get(task_id)
        if not task:
            continue

        response = transcripts[key]["response"]
        og = orig_grades[key]

        # Old L0 verdict (from original grades)
        old_l0_pass = og.get("passed", False)
        if og.get("detection_layer") == 2:
            continue  # Skip grades that went to judge originally

        # New L0 verdict (with context-aware patterns)
        new_result = run_task_patterns(task, response)
        new_l0_pass = new_result.all_required_pass

        # Track section detection
        diag = extract_diagnostic_sections(response)
        if diag is not None:
            section_detected += 1
        else:
            section_not_detected += 1

        total += 1

        # Old confusion matrix
        if old_l0_pass and l2_pass:
            old_tp += 1
        elif old_l0_pass and not l2_pass:
            old_fp += 1
        elif not old_l0_pass and not l2_pass:
            old_tn += 1
        else:
            old_fn += 1

        # New confusion matrix
        if new_l0_pass and l2_pass:
            new_tp += 1
        elif new_l0_pass and not l2_pass:
            new_fp += 1
        elif not new_l0_pass and not l2_pass:
            new_tn += 1
        else:
            new_fn += 1

        # Track flips
        if old_l0_pass and not new_l0_pass:
            if not l2_pass:
                flipped_fp_to_tn.append(key)
            else:
                flipped_tp_to_fn.append(key)

    print("=" * 70)
    print("L0 FALSE-PASS REDUCTION: CONTEXT-AWARE PATTERN MATCHING")
    print("=" * 70)
    print()
    print(f"Total grades analyzed: {total}")
    print(f"Section headers detected: {section_detected}/{total}")
    print(f"  ({section_not_detected} unstructured responses — full-text fallback)")
    print()

    print(f"{'Metric':<35s} {'Old L0':>10s} {'New L0':>10s} {'Delta':>10s}")
    print("-" * 70)
    old_fpr = old_fp / (old_fp + old_tn) if (old_fp + old_tn) > 0 else 0
    new_fpr = new_fp / (new_fp + new_tn) if (new_fp + new_tn) > 0 else 0
    print(f"{'False passes (L0=P, L2=F)':<35s} {old_fp:>10d} {new_fp:>10d} {new_fp - old_fp:>+10d}")
    print(f"{'True passes (L0=P, L2=P)':<35s} {old_tp:>10d} {new_tp:>10d} {new_tp - old_tp:>+10d}")
    print(
        f"{'True negatives (L0=F, L2=F)':<35s} {old_tn:>10d} {new_tn:>10d} {new_tn - old_tn:>+10d}"
    )
    print(
        f"{'False negatives (L0=F, L2=P)':<35s} {old_fn:>10d} {new_fn:>10d} {new_fn - old_fn:>+10d}"
    )
    print(f"{'False-pass rate':<35s} {old_fpr:>9.1%} {new_fpr:>9.1%} {(new_fpr - old_fpr):>+9.1%}")
    print()

    if flipped_fp_to_tn:
        by_task = Counter(k.split(":")[0] for k in flipped_fp_to_tn)
        print(f"Fixed false passes ({len(flipped_fp_to_tn)} grades):")
        for tid, count in by_task.most_common():
            model_tags = [k.split(":")[2] for k in flipped_fp_to_tn if k.startswith(tid)]
            print(f"  {tid}: {count} grades ({', '.join(model_tags)})")
        print()

    if flipped_tp_to_fn:
        by_task = Counter(k.split(":")[0] for k in flipped_tp_to_fn)
        print(f"BROKEN true passes ({len(flipped_tp_to_fn)} grades):")
        for tid, count in by_task.most_common():
            model_tags = [k.split(":")[2] for k in flipped_tp_to_fn if k.startswith(tid)]
            print(f"  {tid}: {count} grades ({', '.join(model_tags)})")
        print()
        print(
            "WARNING: Context-aware matching caused "
            f"{len(flipped_tp_to_fn)} true passes to flip. "
            "Review these tasks for overly strict section scoping."
        )

    # Save
    output = {
        "date": "2026-03-06",
        "analysis": "l0_false_pass_reduction",
        "method": "Context-aware pattern matching: finding patterns scoped to "
        "Primary Diagnosis + Key Findings sections, excluding "
        "Differential and Recommendations",
        "total_grades": total,
        "section_detected": section_detected,
        "section_not_detected": section_not_detected,
        "old": {
            "false_passes": old_fp,
            "true_passes": old_tp,
            "true_negatives": old_tn,
            "false_negatives": old_fn,
            "false_pass_rate": round(old_fpr, 4),
        },
        "new": {
            "false_passes": new_fp,
            "true_passes": new_tp,
            "true_negatives": new_tn,
            "false_negatives": new_fn,
            "false_pass_rate": round(new_fpr, 4),
        },
        "fixed_false_passes": len(flipped_fp_to_tn),
        "broken_true_passes": len(flipped_tp_to_fn),
        "fixed_tasks": dict(Counter(k.split(":")[0] for k in flipped_fp_to_tn).most_common()),
        "broken_tasks": dict(Counter(k.split(":")[0] for k in flipped_tp_to_fn).most_common()),
    }
    with open("results/l0-false-pass-reduction.json", "w") as f:
        json.dump(output, f, indent=2)
    print("Saved to results/l0-false-pass-reduction.json")


if __name__ == "__main__":
    main()
