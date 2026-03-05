#!/usr/bin/env python3
"""Regrade Layer 0-only Opus rc1.0 grades with live GPT-5.2 judge.

Validates the calibration fix and produces corrected pass rates.
"""

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.grading.grader import RubricGrader
from radslice.providers.openai import OpenAIProvider
from radslice.task import load_tasks_from_dir


async def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    judge_provider = OpenAIProvider(api_key=api_key)
    grader = RubricGrader(judge_provider=judge_provider, judge_model="gpt-5.2", pattern_only=False)

    tasks = {t.id: t for t in load_tasks_from_dir("configs/tasks")}

    # Load transcripts
    transcripts = []
    with open("results/eval-20260303-opus46-rc10/transcripts.jsonl") as f:
        for line in f:
            t = json.loads(line)
            if t.get("task_id") and t["task_id"] in tasks:
                transcripts.append(t)

    # Load original grades
    orig = {}
    with open("results/eval-20260303-opus46-rc10/grades.jsonl") as f:
        for line in f:
            g = json.loads(line)
            orig[f"{g['task_id']}:{g['trial']}"] = g

    # Filter to Layer 0-only
    l0_only = [
        t
        for t in transcripts
        if orig.get(f"{t['task_id']}:{t['trial']}", {}).get("detection_layer") == 0
    ]

    print(f"Regrading {len(l0_only)} Layer 0-only Opus grades with GPT-5.2 judge...")
    print()

    results = []
    flipped = []
    new_class_a = []

    for i, t in enumerate(l0_only):
        task = tasks[t["task_id"]]
        result = await grader.grade(task, t["response"], t["model"], int(t["trial"]))
        o = orig[f"{t['task_id']}:{t['trial']}"]

        pr = result.pattern_result
        jr = result.judge_result
        l2_fc = jr.get("failure_class") if jr else None

        was_pass = o["passed"]
        now_pass = result.passed
        flip = "  FLIP" if was_pass != now_pass else ""

        was_str = "PASS" if was_pass else "FAIL"
        now_str = "PASS" if now_pass else "FAIL"

        print(
            f"[{i + 1:2d}/{len(l0_only)}] {result.task_id:10s} t={result.trial} "
            f"was={was_str:4s} now={now_str:4s} "
            f"L2_fc={l2_fc or 'PASS':4s} score={result.weighted_score:.2f}{flip}"
        )

        entry = {
            "task_id": result.task_id,
            "trial": result.trial,
            "model": result.model,
            "was_pass": was_pass,
            "now_pass": now_pass,
            "was_fc": o.get("failure_class"),
            "now_fc": result.failure_class,
            "l0_fc": pr.get("failure_class"),
            "l2_fc": l2_fc,
            "score": result.weighted_score,
            "detection_layer": result.detection_layer,
        }
        results.append(entry)

        if was_pass and not now_pass:
            flipped.append(entry)
            if l2_fc == "A":
                new_class_a.append(entry)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"REGRADE SUMMARY (n={len(l0_only)})")
    print(f"{'=' * 60}")

    was_pass_count = sum(1 for r in results if r["was_pass"])
    now_pass_count = sum(1 for r in results if r["now_pass"])
    print(
        f"Original L0-only passes: {was_pass_count}/{len(results)} "
        f"({was_pass_count / len(results) * 100:.1f}%)"
    )
    print(
        f"Corrected passes: {now_pass_count}/{len(results)} "
        f"({now_pass_count / len(results) * 100:.1f}%)"
    )
    print(f"Flipped pass->fail: {len(flipped)}")
    print(f"New Class A failures: {len(new_class_a)}")

    # Corrected overall Opus pass rate
    # L2 grades (62): 2 passed — unchanged
    corrected_total = 2 + now_pass_count
    print(f"\nCorrected Opus pass rate: {corrected_total}/153 ({corrected_total / 153 * 100:.1f}%)")
    print("Original Opus pass rate: 48/153 (31.4%)")

    if flipped:
        print("\nFlipped grades (pass->fail):")
        fc_dist = Counter(r["l2_fc"] for r in flipped)
        for fc, count in fc_dist.most_common():
            print(f"  Class {fc or 'PASS'}: {count}")
        print()
        for r in flipped:
            print(
                f"  {r['task_id']:10s} t={r['trial']} "
                f"L2={r['l2_fc'] or 'PASS':4s} score={r['score']:.2f}"
            )

    if new_class_a:
        print("\nNEW CLASS A FAILURES (require risk debt entries):")
        new_a_tasks = {}
        for r in new_class_a:
            tid = r["task_id"]
            if tid not in new_a_tasks:
                new_a_tasks[tid] = []
            new_a_tasks[tid].append(r)

        for tid, trials in new_a_tasks.items():
            task = tasks[tid]
            print(
                f"  {tid:10s} ({len(trials)}/3 Class A) "
                f"condition={task.ground_truth.primary_diagnosis} "
                f"modality={task.modality}"
            )

    # Save results
    output_path = "results/calibration-regrade-l0only-20260305.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "campaign": "calibration-regrade-l0only-20260305",
                "date": "2026-03-05",
                "method": "Regrade 91 Layer 0-only Opus grades with live GPT-5.2 judge",
                "n_regraded": len(results),
                "original_l0_pass_count": was_pass_count,
                "corrected_l0_pass_count": now_pass_count,
                "flipped_count": len(flipped),
                "new_class_a_count": len(new_class_a),
                "corrected_opus_total_pass": corrected_total,
                "corrected_opus_pass_rate": round(corrected_total / 153, 4),
                "original_opus_pass_rate": round(48 / 153, 4),
                "grades": results,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
