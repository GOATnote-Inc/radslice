#!/usr/bin/env python3
"""Judge concordance analysis for the 40 unsolved tasks.

For each unsolved task, compares:
- GPT-5.2 grades (judged by Opus 4.6)
- Opus 4.6 grades (judged by GPT-5.2 for L0-only, original for L2)

Questions answered:
1. Do both judges agree these tasks are unsolvable?
2. Are any tasks judge-dependent (one judge passes, other fails)?
3. What failure classes dominate the unsolved set?
4. Are IMAGE_MISMATCH tasks driving the unsolved count?
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    # Load GPT regrade (all 153 grades, judged by Opus)
    with open("results/regrade-gpt52-rc10-20260306.json") as f:
        gpt_regrade = json.load(f)

    # Load Opus L0-only regrade (91 grades, judged by GPT-5.2)
    with open("results/calibration-regrade-l0only-20260305.json") as f:
        opus_l0_regrade = json.load(f)

    # Load Opus original grades (includes L2 grades)
    opus_orig = {}
    with open("results/eval-20260303-opus46-rc10/grades.jsonl") as f:
        for line in f:
            g = json.loads(line)
            key = f"{g['task_id']}:{g['trial']}"
            opus_orig[key] = g

    # Load comparison for unsolved task list
    with open("results/rc10-corrected-comparison.json") as f:
        comparison = json.load(f)

    unsolved = comparison["task_level"]["unsolved_tasks"]

    # Known IMAGE_MISMATCH tasks
    image_mismatch = {"CT-027", "CT-048", "CT-097", "MRI-007", "MRI-031", "MRI-035"}

    # Build per-task grade maps
    # GPT grades (judged by Opus)
    gpt_by_task = defaultdict(list)
    for g in gpt_regrade["grades"]:
        gpt_by_task[g["task_id"]].append(g)

    # Opus grades: combine L0 regrade + L2 originals
    opus_by_task = defaultdict(list)
    for g in opus_l0_regrade["grades"]:
        opus_by_task[g["task_id"]].append(g)
    # Add L2 original grades
    for key, g in opus_orig.items():
        if g.get("detection_layer") == 2:
            opus_by_task[g["task_id"]].append(
                {
                    "task_id": g["task_id"],
                    "trial": g["trial"],
                    "model": "opus-4-6",
                    "was_pass": g["passed"],
                    "now_pass": g["passed"],  # L2 grades unchanged
                    "was_fc": g.get("failure_class"),
                    "now_fc": g.get("failure_class"),
                    "l0_fc": None,
                    "l2_fc": g.get("failure_class"),
                    "score": g.get("weighted_score", 0),
                    "detection_layer": 2,
                    "source": "original_l2",
                }
            )

    print("=" * 78)
    print("JUDGE CONCORDANCE ANALYSIS — 40 UNSOLVED TASKS")
    print("=" * 78)
    print()

    # Categorize unsolved tasks
    categories = {
        "both_judges_agree_fail": [],  # Both judges fail all trials for both models
        "judge_dependent": [],  # One judge would pass, other fails
        "image_mismatch": [],  # Known data quality issues
        "score_near_threshold": [],  # Any trial scored 0.40-0.50
    }

    # Failure class analysis
    gpt_l2_classes = Counter()
    opus_l2_classes = Counter()
    gpt_l0_classes = Counter()
    opus_l0_classes = Counter()

    # Score distributions
    gpt_scores = []
    opus_scores = []

    print(
        f"{'Task':<12s} {'ImgMM':>5s} {'GPT scores':>20s} {'Opus scores':>20s} "
        f"{'GPT L2fc':>10s} {'Opus L2fc':>10s} {'Near?':>5s}"
    )
    print("-" * 78)

    for tid in sorted(unsolved):
        is_mismatch = tid in image_mismatch
        gpt_grades = gpt_by_task.get(tid, [])
        opus_grades = opus_by_task.get(tid, [])

        # Scores
        g_scores = [g["score"] for g in gpt_grades]
        o_scores = [g["score"] for g in opus_grades]
        gpt_scores.extend(g_scores)
        opus_scores.extend(o_scores)

        # L2 failure classes
        g_fcs = [g.get("l2_fc") or g.get("now_fc") or "?" for g in gpt_grades]
        o_fcs = [g.get("l2_fc") or g.get("now_fc") or "?" for g in opus_grades]
        for fc in g_fcs:
            gpt_l2_classes[fc] += 1
        for fc in o_fcs:
            opus_l2_classes[fc] += 1

        # L0 failure classes
        for g in gpt_grades:
            if g.get("l0_fc"):
                gpt_l0_classes[g["l0_fc"]] += 1
        for g in opus_grades:
            if g.get("l0_fc"):
                opus_l0_classes[g["l0_fc"]] += 1

        # Near threshold?
        near = any(0.40 <= s <= 0.50 for s in g_scores + o_scores)

        # Any pass from original L0?
        gpt_any_l0_pass = any(g.get("was_pass") for g in gpt_grades)
        opus_any_l0_pass = any(g.get("was_pass") for g in opus_grades)

        g_score_str = ",".join(f"{s:.2f}" for s in sorted(g_scores))
        o_score_str = ",".join(f"{s:.2f}" for s in sorted(o_scores))
        g_fc_str = ",".join(sorted(set(g_fcs)))
        o_fc_str = ",".join(sorted(set(o_fcs)))

        print(
            f"{tid:<12s} {'YES' if is_mismatch else '':>5s} "
            f"{g_score_str:>20s} {o_score_str:>20s} "
            f"{g_fc_str:>10s} {o_fc_str:>10s} "
            f"{'NEAR' if near else '':>5s}"
        )

        if is_mismatch:
            categories["image_mismatch"].append(tid)
        if near:
            categories["score_near_threshold"].append(tid)

        # Check judge dependency: did L0 pass but L2 fail?
        if gpt_any_l0_pass or opus_any_l0_pass:
            categories["judge_dependent"].append(
                {
                    "task_id": tid,
                    "gpt_l0_passed": gpt_any_l0_pass,
                    "opus_l0_passed": opus_any_l0_pass,
                    "gpt_l2_all_fail": all(not g["now_pass"] for g in gpt_grades)
                    if gpt_grades
                    else True,
                    "opus_l2_all_fail": all(not g["now_pass"] for g in opus_grades)
                    if opus_grades
                    else True,
                }
            )

    # Judge asymmetry deep dive
    print()
    print("=" * 78)
    print("FAILURE CLASS DISTRIBUTION (unsolved tasks only)")
    print("=" * 78)
    print()
    print("GPT grades (judged by Opus):")
    for fc, count in gpt_l2_classes.most_common():
        print(f"  Class {fc}: {count}")
    print()
    print("Opus grades (judged by GPT-5.2):")
    for fc, count in opus_l2_classes.most_common():
        print(f"  Class {fc}: {count}")

    # Score statistics
    print()
    print("=" * 78)
    print("SCORE STATISTICS (unsolved tasks)")
    print("=" * 78)
    if gpt_scores:
        print(
            f"GPT:  mean={sum(gpt_scores) / len(gpt_scores):.3f}  "
            f"max={max(gpt_scores):.3f}  "
            f"min={min(gpt_scores):.3f}  "
            f"n={len(gpt_scores)}"
        )
    if opus_scores:
        print(
            f"Opus: mean={sum(opus_scores) / len(opus_scores):.3f}  "
            f"max={max(opus_scores):.3f}  "
            f"min={min(opus_scores):.3f}  "
            f"n={len(opus_scores)}"
        )

    # Near-threshold analysis
    near_tasks = categories["score_near_threshold"]
    print(f"\nNear-threshold (0.40-0.50): {len(near_tasks)} tasks")
    if near_tasks:
        print(f"  Tasks: {', '.join(near_tasks)}")
        print("  These could flip with minor prompt changes or different judge calibration.")

    # IMAGE_MISMATCH overlap
    mm_tasks = categories["image_mismatch"]
    print(f"\nIMAGE_MISMATCH tasks in unsolved: {len(mm_tasks)}/40")
    if mm_tasks:
        print(f"  Tasks: {', '.join(mm_tasks)}")
        print("  These are data quality issues, not model failures.")

    # Judge dependency
    jd = categories["judge_dependent"]
    print(f"\nJudge-dependent tasks (L0 passed but L2 failed): {len(jd)}")
    if jd:
        for entry in jd:
            tid = entry["task_id"]
            gpt_note = "GPT L0 passed" if entry["gpt_l0_passed"] else ""
            opus_note = "Opus L0 passed" if entry["opus_l0_passed"] else ""
            notes = ", ".join(filter(None, [gpt_note, opus_note]))
            print(f"  {tid}: {notes}")

    # True unsolved (excluding IMAGE_MISMATCH)
    true_unsolved = [t for t in unsolved if t not in image_mismatch]
    near_not_mm = [t for t in near_tasks if t not in image_mismatch]

    print()
    print("=" * 78)
    print("CONCORDANCE SUMMARY")
    print("=" * 78)
    print(f"Total unsolved tasks:              {len(unsolved)}")
    print(f"  IMAGE_MISMATCH (data quality):   {len(mm_tasks)}")
    print(f"  True unsolved (model failures):  {len(true_unsolved)}")
    print(f"  Near-threshold (may flip):        {len(near_not_mm)}")
    print(f"  Firmly unsolved:                  {len(true_unsolved) - len(near_not_mm)}")
    print()

    # L0 vs L2 disagreement rate for unsolved
    l0_pass_l2_fail = 0
    l0_fail_l2_fail = 0
    total_grades = 0
    for tid in unsolved:
        for g in gpt_by_task.get(tid, []):
            total_grades += 1
            if g.get("was_pass") and not g["now_pass"]:
                l0_pass_l2_fail += 1
            elif not g.get("was_pass") and not g["now_pass"]:
                l0_fail_l2_fail += 1
        for g in opus_by_task.get(tid, []):
            if g.get("source") == "original_l2":
                continue
            total_grades += 1
            if g.get("was_pass") and not g["now_pass"]:
                l0_pass_l2_fail += 1
            elif not g.get("was_pass") and not g["now_pass"]:
                l0_fail_l2_fail += 1

    print(f"Among unsolved task grades (n={total_grades}):")
    l0f_pct = l0_fail_l2_fail / total_grades * 100
    l0p_pct = l0_pass_l2_fail / total_grades * 100
    print(f"  L0 FAIL + L2 FAIL (both agree):  {l0_fail_l2_fail} ({l0f_pct:.0f}%)")
    print(f"  L0 PASS + L2 FAIL (judge caught): {l0_pass_l2_fail} ({l0p_pct:.0f}%)")
    print()

    # Modality breakdown
    modality_counts = Counter()
    for tid in true_unsolved:
        prefix = tid.split("-")[0]
        modality_counts[prefix] += 1
    print("True unsolved by modality:")
    for mod, count in modality_counts.most_common():
        print(f"  {mod}: {count}")

    # Save
    output = {
        "date": "2026-03-06",
        "analysis": "judge_concordance",
        "unsolved_count": len(unsolved),
        "image_mismatch_count": len(mm_tasks),
        "image_mismatch_tasks": mm_tasks,
        "true_unsolved_count": len(true_unsolved),
        "true_unsolved_tasks": true_unsolved,
        "near_threshold_count": len(near_not_mm),
        "near_threshold_tasks": near_not_mm,
        "firmly_unsolved_count": len(true_unsolved) - len(near_not_mm),
        "judge_dependent_count": len(jd),
        "judge_dependent": jd,
        "l0_pass_l2_fail_in_unsolved": l0_pass_l2_fail,
        "l0_fail_l2_fail_in_unsolved": l0_fail_l2_fail,
        "gpt_failure_classes": dict(gpt_l2_classes),
        "opus_failure_classes": dict(opus_l2_classes),
        "gpt_score_stats": {
            "mean": round(sum(gpt_scores) / len(gpt_scores), 4) if gpt_scores else None,
            "max": round(max(gpt_scores), 4) if gpt_scores else None,
            "min": round(min(gpt_scores), 4) if gpt_scores else None,
            "n": len(gpt_scores),
        },
        "opus_score_stats": {
            "mean": round(sum(opus_scores) / len(opus_scores), 4) if opus_scores else None,
            "max": round(max(opus_scores), 4) if opus_scores else None,
            "min": round(min(opus_scores), 4) if opus_scores else None,
            "n": len(opus_scores),
        },
        "modality_breakdown": dict(modality_counts),
    }

    with open("results/judge-concordance-unsolved.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\nSaved to results/judge-concordance-unsolved.json")


if __name__ == "__main__":
    main()
