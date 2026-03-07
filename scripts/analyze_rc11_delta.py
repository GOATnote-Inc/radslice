#!/usr/bin/env python3
"""rc1.0 → rc1.1 per-task delta analysis.

Compares grades for the 44 overlapping tasks between rc1.0 (L0 pattern-only)
and rc1.1 (L2 judge always invoked). Categorizes each task as STABLE_PASS,
STABLE_FAIL, DEGRADED, or IMPROVED.

Usage:
    .venv/bin/python3 scripts/analyze_rc11_delta.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RC10_GPT = REPO_ROOT / "results" / "eval-20260303-gpt52-rc10"
RC10_OPUS = REPO_ROOT / "results" / "eval-20260303-opus46-rc10"
RC11_GPT = REPO_ROOT / "results" / "eval-20260307-gpt52-rc11"
RC11_OPUS = REPO_ROOT / "results" / "eval-20260307-opus46-rc11"
OUTPUT_PATH = REPO_ROOT / "results" / "rc11-delta-analysis.json"


def load_grades(results_dir: Path) -> dict[str, list[dict]]:
    """Load grades.jsonl → {task_id: [grade_dicts]}."""
    grades: dict[str, list[dict]] = defaultdict(list)
    with open(results_dir / "grades.jsonl") as f:
        for line in f:
            if line.strip():
                g = json.loads(line)
                grades[g["task_id"]].append(g)
    for task_id in grades:
        grades[task_id].sort(key=lambda g: g.get("trial", 0))
    return dict(grades)


def categorize(rc10_passes: int, rc11_passes: int, n_trials: int = 3) -> str:
    """Categorize delta: STABLE_PASS, STABLE_FAIL, DEGRADED, IMPROVED."""
    rc10_pass = rc10_passes > 0
    rc11_pass = rc11_passes > 0
    if rc10_pass and rc11_pass:
        return "STABLE_PASS"
    if not rc10_pass and not rc11_pass:
        return "STABLE_FAIL"
    if rc10_pass and not rc11_pass:
        return "DEGRADED"
    return "IMPROVED"


def analyze_model(
    rc10_grades: dict[str, list[dict]],
    rc11_grades: dict[str, list[dict]],
    model_name: str,
) -> list[dict]:
    """Per-task delta analysis for one model."""
    # Only compare tasks present in both
    overlap = sorted(set(rc10_grades.keys()) & set(rc11_grades.keys()))
    results = []

    for task_id in overlap:
        rc10_trials = rc10_grades[task_id]
        rc11_trials = rc11_grades[task_id]

        rc10_passes = sum(1 for g in rc10_trials if g.get("passed"))
        rc11_passes = sum(1 for g in rc11_trials if g.get("passed"))

        rc10_layers = [g.get("detection_layer", -1) for g in rc10_trials]
        rc11_layers = [g.get("detection_layer", -1) for g in rc11_trials]

        rc10_scores = [g.get("weighted_score", 0) for g in rc10_trials]
        rc11_scores = [g.get("weighted_score", 0) for g in rc11_trials]

        rc10_classes = [g.get("failure_class") for g in rc10_trials]
        rc11_classes = [g.get("failure_class") for g in rc11_trials]

        category = categorize(rc10_passes, rc11_passes)

        # Check if rc1.0 passes were L0-only (pattern inflation)
        rc10_pass_layers = [g.get("detection_layer", -1) for g in rc10_trials if g.get("passed")]
        rc10_passes_were_l0 = (
            all(layer == 0 for layer in rc10_pass_layers) if rc10_pass_layers else False
        )

        entry = {
            "task_id": task_id,
            "model": model_name,
            "category": category,
            "rc10_passes": f"{rc10_passes}/{len(rc10_trials)}",
            "rc11_passes": f"{rc11_passes}/{len(rc11_trials)}",
            "rc10_detection_layers": rc10_layers,
            "rc11_detection_layers": rc11_layers,
            "rc10_mean_score": round(sum(rc10_scores) / len(rc10_scores), 4),
            "rc11_mean_score": round(sum(rc11_scores) / len(rc11_scores), 4),
            "score_delta": round(
                sum(rc11_scores) / len(rc11_scores) - sum(rc10_scores) / len(rc10_scores),
                4,
            ),
            "rc10_failure_classes": rc10_classes,
            "rc11_failure_classes": rc11_classes,
            "rc10_passes_were_l0_only": rc10_passes_were_l0,
        }
        results.append(entry)

    return results


def compute_summary(gpt_deltas: list[dict], opus_deltas: list[dict]) -> dict:
    """Compute aggregate statistics."""
    summary = {}
    for model_name, deltas in [("gpt52", gpt_deltas), ("opus46", opus_deltas)]:
        cats = Counter(d["category"] for d in deltas)
        degraded = [d for d in deltas if d["category"] == "DEGRADED"]
        degraded_from_l0 = sum(1 for d in degraded if d["rc10_passes_were_l0_only"])

        summary[model_name] = {
            "n_tasks": len(deltas),
            "STABLE_PASS": cats.get("STABLE_PASS", 0),
            "STABLE_FAIL": cats.get("STABLE_FAIL", 0),
            "DEGRADED": cats.get("DEGRADED", 0),
            "IMPROVED": cats.get("IMPROVED", 0),
            "degraded_from_l0_only": degraded_from_l0,
            "degraded_task_ids": [d["task_id"] for d in degraded],
            "improved_task_ids": [d["task_id"] for d in deltas if d["category"] == "IMPROVED"],
            "mean_score_delta": round(sum(d["score_delta"] for d in deltas) / len(deltas), 4)
            if deltas
            else 0,
        }

    # Cross-model: tasks that both models DEGRADED on
    gpt_deg = set(summary["gpt52"]["degraded_task_ids"])
    opus_deg = set(summary["opus46"]["degraded_task_ids"])
    summary["both_degraded"] = sorted(gpt_deg & opus_deg)
    summary["gpt_only_degraded"] = sorted(gpt_deg - opus_deg)
    summary["opus_only_degraded"] = sorted(opus_deg - gpt_deg)

    # Always-fail in rc1.1 (both models, all trials)
    rc11_fail_gpt = {d["task_id"] for d in gpt_deltas if d["rc11_passes"] == "0/3"}
    rc11_fail_opus = {d["task_id"] for d in opus_deltas if d["rc11_passes"] == "0/3"}
    summary["always_fail_both_rc11"] = sorted(rc11_fail_gpt & rc11_fail_opus)

    return summary


def print_report(gpt_deltas: list[dict], opus_deltas: list[dict], summary: dict) -> None:
    """Print human-readable delta report."""
    W = 72
    print("=" * W)
    print("  RC1.0 → RC1.1 DELTA ANALYSIS")
    print("=" * W)
    print()

    for model, key in [("GPT-5.2", "gpt52"), ("Opus 4.6", "opus46")]:
        s = summary[key]
        print(f"  {model} ({s['n_tasks']} tasks):")
        print(f"    STABLE_PASS:  {s['STABLE_PASS']:3d}")
        print(f"    STABLE_FAIL:  {s['STABLE_FAIL']:3d}")
        deg = s["DEGRADED"]
        l0_only = s["degraded_from_l0_only"]
        print(f"    DEGRADED:     {deg:3d}  (of which {l0_only} were L0-only passes)")
        print(f"    IMPROVED:     {s['IMPROVED']:3d}")
        print(f"    Mean score Δ: {s['mean_score_delta']:+.4f}")
        print()

    # Show DEGRADED tasks
    for model_name, deltas in [("GPT-5.2", gpt_deltas), ("Opus 4.6", opus_deltas)]:
        degraded = [d for d in deltas if d["category"] == "DEGRADED"]
        if degraded:
            print(f"  DEGRADED tasks ({model_name}):")
            for d in sorted(degraded, key=lambda x: x["score_delta"]):
                l0 = " [L0-only]" if d["rc10_passes_were_l0_only"] else ""
                print(
                    f"    {d['task_id']:12s}  {d['rc10_passes']}→{d['rc11_passes']}  "
                    f"Δ={d['score_delta']:+.4f}  rc11_class={d['rc11_failure_classes']}{l0}"
                )
            print()

    # Show IMPROVED tasks
    for model_name, deltas in [("GPT-5.2", gpt_deltas), ("Opus 4.6", opus_deltas)]:
        improved = [d for d in deltas if d["category"] == "IMPROVED"]
        if improved:
            print(f"  IMPROVED tasks ({model_name}):")
            for d in sorted(improved, key=lambda x: -x["score_delta"]):
                print(
                    f"    {d['task_id']:12s}  {d['rc10_passes']}→{d['rc11_passes']}  "
                    f"Δ={d['score_delta']:+.4f}"
                )
            print()

    print(f"  Always-fail both models (rc1.1): {len(summary['always_fail_both_rc11'])} tasks")
    if summary["always_fail_both_rc11"]:
        print(f"    {', '.join(summary['always_fail_both_rc11'])}")
    print()
    print("=" * W)


def main():
    print("Loading grades...")
    rc10_gpt = load_grades(RC10_GPT)
    rc10_opus = load_grades(RC10_OPUS)
    rc11_gpt = load_grades(RC11_GPT)
    rc11_opus = load_grades(RC11_OPUS)

    print("Analyzing GPT-5.2 delta...")
    gpt_deltas = analyze_model(rc10_gpt, rc11_gpt, "gpt-5.2")
    print("Analyzing Opus 4.6 delta...")
    opus_deltas = analyze_model(rc10_opus, rc11_opus, "opus-4-6")

    summary = compute_summary(gpt_deltas, opus_deltas)

    # Only tasks in rc1.0 but not rc1.1
    rc10_only = sorted(set(rc10_gpt.keys()) - set(rc11_gpt.keys()))
    summary["excluded_from_rc11"] = rc10_only

    output = {
        "campaign": "rc11-delta-analysis",
        "date": "2026-03-07",
        "description": (
            "Per-task comparison of rc1.0 (L0 pattern-only) vs rc1.1 (L2 judge always invoked)"
        ),
        "summary": summary,
        "gpt52_deltas": gpt_deltas,
        "opus46_deltas": opus_deltas,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nOutput written to {OUTPUT_PATH}")

    print()
    print_report(gpt_deltas, opus_deltas, summary)


if __name__ == "__main__":
    main()
