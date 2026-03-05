#!/usr/bin/env python3
"""Regrade stored transcripts with a cross-vendor LLM judge.

Usage:
    python scripts/regrade_with_judge.py \
        --transcripts results/eval-20260303-gpt52-rc10/transcripts.jsonl \
        --grades results/eval-20260303-gpt52-rc10/grades.jsonl \
        --judge-provider openai|anthropic \
        --judge-model gpt-5.2|claude-opus-4-6 \
        --output results/regrade-gpt52-rc10-20260306.json
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.grading.grader import RubricGrader
from radslice.task import load_tasks_from_dir


def _get_provider(provider_name: str):
    if provider_name == "openai":
        from radslice.providers.openai import OpenAIProvider

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            print("OPENAI_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        return OpenAIProvider(api_key=key)
    elif provider_name == "anthropic":
        from radslice.providers.anthropic import AnthropicProvider

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("ANTHROPIC_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        return AnthropicProvider(api_key=key)
    else:
        print(f"Unknown provider: {provider_name}", file=sys.stderr)
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Regrade transcripts with LLM judge")
    parser.add_argument("--transcripts", required=True, help="Path to transcripts.jsonl")
    parser.add_argument("--grades", required=True, help="Path to original grades.jsonl")
    parser.add_argument("--judge-provider", required=True, choices=["openai", "anthropic"])
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--layer0-only", action="store_true", help="Only regrade Layer 0 grades")
    args = parser.parse_args()

    judge_provider = _get_provider(args.judge_provider)
    grader = RubricGrader(
        judge_provider=judge_provider, judge_model=args.judge_model, pattern_only=False
    )

    tasks = {t.id: t for t in load_tasks_from_dir("configs/tasks")}

    # Load transcripts
    transcripts = []
    with open(args.transcripts) as f:
        for line in f:
            t = json.loads(line)
            if t.get("task_id") and t["task_id"] in tasks:
                transcripts.append(t)

    # Load original grades
    orig = {}
    with open(args.grades) as f:
        for line in f:
            g = json.loads(line)
            orig[f"{g['task_id']}:{g['trial']}"] = g

    # Filter if requested
    if args.layer0_only:
        transcripts = [
            t
            for t in transcripts
            if orig.get(f"{t['task_id']}:{t['trial']}", {}).get("detection_layer") == 0
        ]

    print(f"Regrading {len(transcripts)} transcripts with {args.judge_model} judge...")
    print()

    results = []
    flipped = []
    new_class_a = []

    for i, t in enumerate(transcripts):
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
            f"[{i + 1:3d}/{len(transcripts)}] {result.task_id:10s} t={result.trial} "
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
    n = len(results)
    was_pass_count = sum(1 for r in results if r["was_pass"])
    now_pass_count = sum(1 for r in results if r["now_pass"])

    print(f"\n{'=' * 60}")
    print(f"REGRADE SUMMARY (n={n})")
    print(f"{'=' * 60}")
    print(f"Original passes: {was_pass_count}/{n} ({was_pass_count / n * 100:.1f}%)")
    print(f"Corrected passes: {now_pass_count}/{n} ({now_pass_count / n * 100:.1f}%)")
    print(f"Flipped pass->fail: {len(flipped)}")
    print(f"Flipped fail->pass: {sum(1 for r in results if not r['was_pass'] and r['now_pass'])}")
    print(f"New Class A: {len(new_class_a)}")

    if flipped:
        print("\nFlipped pass->fail by class:")
        fc_dist = Counter(r["l2_fc"] for r in flipped)
        for fc, count in fc_dist.most_common():
            print(f"  Class {fc or 'PASS'}: {count}")
        print()
        # Group by task
        task_flips = {}
        for r in flipped:
            tid = r["task_id"]
            if tid not in task_flips:
                task_flips[tid] = []
            task_flips[tid].append(r)
        for tid, trials in sorted(task_flips.items()):
            fcs = [r["l2_fc"] for r in trials]
            print(f"  {tid:10s} {len(trials)}/3 flipped, L2 classes: {fcs}")

    # Save
    output = {
        "campaign": Path(args.output).stem,
        "date": "2026-03-06",
        "source_transcripts": args.transcripts,
        "source_grades": args.grades,
        "judge_model": args.judge_model,
        "judge_provider": args.judge_provider,
        "n_regraded": n,
        "original_pass_count": was_pass_count,
        "corrected_pass_count": now_pass_count,
        "original_pass_rate": round(was_pass_count / n, 4),
        "corrected_pass_rate": round(now_pass_count / n, 4),
        "flipped_pass_to_fail": len(flipped),
        "flipped_fail_to_pass": sum(1 for r in results if not r["was_pass"] and r["now_pass"]),
        "new_class_a_count": len(new_class_a),
        "grades": results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
