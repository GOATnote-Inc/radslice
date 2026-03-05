#!/usr/bin/env python3
"""Produce corrected cross-model comparison from regrade results."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    with open("results/regrade-gpt52-rc10-20260306.json") as f:
        gpt = json.load(f)
    with open("results/calibration-regrade-l0only-20260305.json") as f:
        opus_l0 = json.load(f)

    # Opus corrected: 2 (L2 original passes) + corrected L0 passes
    opus_corrected_pass = 2 + opus_l0["corrected_l0_pass_count"]
    gpt_pass = gpt["corrected_pass_count"]
    gpt_rate = gpt["corrected_pass_rate"]
    opus_rate = opus_corrected_pass / 153

    print("=" * 70)
    print("CORRECTED RC1.0 CROSS-MODEL COMPARISON")
    print("=" * 70)
    print()

    gpt_str = f"{gpt_pass}/153 ({gpt_rate * 100:.1f}%)"
    opus_str = f"{opus_corrected_pass}/153 ({opus_rate * 100:.1f}%)"

    print(f"{'Metric':<30s} {'Original':>18s} {'Corrected':>18s}")
    print("-" * 70)
    print(f"{'GPT-5.2 pass rate':<30s} {'86/153 (56.2%)':>18s} {gpt_str:>18s}")
    print(f"{'Opus 4.6 pass rate':<30s} {'48/153 (31.4%)':>18s} {opus_str:>18s}")
    print(f"{'GPT:Opus ratio':<30s} {'1.8x':>18s} {f'{gpt_pass / opus_corrected_pass:.1f}x':>18s}")
    print(f"{'GPT flipped pass->fail':<30s} {'—':>18s} {gpt['flipped_pass_to_fail']:>18d}")
    print(f"{'Opus flipped pass->fail':<30s} {'—':>18s} {27:>18d}")
    print()

    # Per-task comparison
    gpt_tasks = {}
    for g in gpt["grades"]:
        tid = g["task_id"]
        if tid not in gpt_tasks:
            gpt_tasks[tid] = {"pass": 0, "total": 0}
        gpt_tasks[tid]["total"] += 1
        if g["now_pass"]:
            gpt_tasks[tid]["pass"] += 1

    opus_tasks = {}
    for g in opus_l0["grades"]:
        tid = g["task_id"]
        if tid not in opus_tasks:
            opus_tasks[tid] = {"pass": 0, "total": 0}
        opus_tasks[tid]["total"] += 1
        if g["now_pass"]:
            opus_tasks[tid]["pass"] += 1

    # Add L2 original Opus grades
    with open("results/eval-20260303-opus46-rc10/grades.jsonl") as f:
        for line in f:
            g = json.loads(line)
            if g["detection_layer"] == 2:
                tid = g["task_id"]
                if tid not in opus_tasks:
                    opus_tasks[tid] = {"pass": 0, "total": 0}
                opus_tasks[tid]["total"] += 1
                if g["passed"]:
                    opus_tasks[tid]["pass"] += 1

    all_tasks = sorted(set(gpt_tasks) | set(opus_tasks))
    both_pass = 0
    both_fail = 0
    gpt_only = 0
    opus_only = 0
    unsolved = []

    print(f"{'Task':<12s} {'GPT':>8s} {'Opus':>8s} {'Verdict':>14s}")
    print("-" * 45)
    for tid in all_tasks:
        gp = gpt_tasks.get(tid, {"pass": 0, "total": 3})
        op = opus_tasks.get(tid, {"pass": 0, "total": 3})
        gpt_any = gp["pass"] > 0
        opus_any = op["pass"] > 0

        if gpt_any and opus_any:
            verdict = "both_pass"
            both_pass += 1
        elif not gpt_any and not opus_any:
            verdict = "UNSOLVED"
            both_fail += 1
            unsolved.append(tid)
        elif gpt_any:
            verdict = "GPT_only"
            gpt_only += 1
        else:
            verdict = "Opus_only"
            opus_only += 1

        print(
            f"{tid:<12s} {gp['pass']}/{gp['total']}   {op['pass']}/{op['total']}   {verdict:>14s}"
        )

    print()
    print(f"Both pass: {both_pass}")
    print(f"Both fail (unsolved): {both_fail}")
    print(f"GPT-only pass: {gpt_only}")
    print(f"Opus-only pass: {opus_only}")
    print(f"\nUnsolved tasks ({both_fail}): {', '.join(unsolved)}")

    # Save
    comparison = {
        "date": "2026-03-06",
        "original": {
            "gpt52": {"pass": 86, "total": 153, "rate": 0.562},
            "opus46": {"pass": 48, "total": 153, "rate": 0.314},
            "ratio": 1.79,
            "note": "All grades from Layer 0 patterns only. No LLM judge validation.",
        },
        "corrected": {
            "gpt52": {
                "pass": gpt_pass,
                "total": 153,
                "rate": gpt_rate,
                "judge": "claude-opus-4-6",
                "flipped": gpt["flipped_pass_to_fail"],
            },
            "opus46": {
                "pass": opus_corrected_pass,
                "total": 153,
                "rate": round(opus_rate, 4),
                "judge": "gpt-5.2",
                "flipped": 27,
            },
            "ratio": round(gpt_pass / opus_corrected_pass, 2) if opus_corrected_pass > 0 else None,
        },
        "task_level": {
            "both_pass": both_pass,
            "both_fail": both_fail,
            "gpt_only_pass": gpt_only,
            "opus_only_pass": opus_only,
            "unsolved_tasks": unsolved,
        },
    }
    with open("results/rc10-corrected-comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)

    print("\nSaved to results/rc10-corrected-comparison.json")


if __name__ == "__main__":
    main()
