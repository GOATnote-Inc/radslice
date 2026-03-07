#!/usr/bin/env python3
"""Solvability audit: feed each rc1.1 task's reference_solution through the judge.

Rationale (Anthropic eval best practice): "Each task must have a known working
output that passes all graders." If the reference solution itself can't pass
the judge, the task is broken — not the model.

Usage:
    .venv/bin/python3 scripts/audit_rc11_solvability.py

Requires OPENAI_API_KEY and ANTHROPIC_API_KEY in environment.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "configs" / "tasks"
GPT_RC11 = REPO_ROOT / "results" / "eval-20260307-gpt52-rc11"
OPUS_RC11 = REPO_ROOT / "results" / "eval-20260307-opus46-rc11"
OUTPUT_PATH = REPO_ROOT / "results" / "rc11-solvability-audit.json"


# ---------------------------------------------------------------------------
# Task loading (lightweight, no full radslice import needed)
# ---------------------------------------------------------------------------
def get_rc11_task_ids() -> set[str]:
    """Extract unique task IDs from rc1.1 grade files."""
    task_ids = set()
    for d in [GPT_RC11, OPUS_RC11]:
        with open(d / "grades.jsonl") as f:
            for line in f:
                if line.strip():
                    task_ids.add(json.loads(line)["task_id"])
    return task_ids


def load_task_yaml(task_id: str) -> dict:
    """Load task YAML by ID, searching modality subdirectories."""
    for subdir in ["xray", "ct", "mri", "ultrasound", "incidental", "audit"]:
        path = TASKS_DIR / subdir / f"{task_id}.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"Task YAML not found: {task_id}")


# ---------------------------------------------------------------------------
# Judge invocation
# ---------------------------------------------------------------------------
async def judge_reference_solution(task_data: dict) -> dict:
    """Run the LLM judge on a task's reference_solution.

    Uses the radslice grading pipeline directly to ensure consistency
    with the actual eval.
    """
    from radslice.grading.dimensions import weighted_score
    from radslice.grading.judge import run_judge

    task_id = task_data["id"]
    task_type = task_data.get("task_type", "diagnosis")
    gt = task_data["ground_truth"]
    ref_solution = task_data.get("reference_solution", "")

    if not ref_solution or not ref_solution.strip():
        return {
            "task_id": task_id,
            "has_reference_solution": False,
            "error": "No reference solution",
        }

    # Build ground_truth dict matching grader._run_judge format
    ground_truth = {
        "primary_diagnosis": gt.get("primary_diagnosis", ""),
        "differential": gt.get("differential", []),
        "severity": gt.get("severity", ""),
        "laterality": gt.get("laterality", ""),
        "key_findings": gt.get("key_findings", []),
        "negatives": gt.get("negatives", []),
    }

    if gt.get("incidental_findings"):
        ground_truth["incidental_findings"] = gt["incidental_findings"]
    if gt.get("report_errors"):
        ground_truth["report_errors"] = gt["report_errors"]
    if gt.get("provided_report"):
        ground_truth["provided_report"] = gt["provided_report"]

    # Determine judge model and provider based on cross-vendor rule:
    # GPT transcripts were judged by Opus, Opus transcripts by GPT.
    # For solvability, use both judges and take the stricter.
    # But for simplicity, use GPT-5.2 as judge (matches Opus eval judge).
    judge_model = "gpt-5.2"
    provider = _get_provider("openai")

    try:
        result = await run_judge(
            provider=provider,
            judge_model=judge_model,
            task_name=task_data.get("name", task_id),
            ground_truth=ground_truth,
            model_response=ref_solution,
            reference_solution=ref_solution,
            task_type=task_type,
        )
    except Exception as e:
        return {
            "task_id": task_id,
            "has_reference_solution": True,
            "error": str(e),
        }

    w_score = weighted_score(result.dimension_scores)

    # Determine pass using same logic as grader._determine_pass
    failure_class = result.failure_class
    if failure_class in ("A", "B"):
        passed = False
    else:
        passed = w_score >= 0.5

    return {
        "task_id": task_id,
        "has_reference_solution": True,
        "passed": passed,
        "weighted_score": round(w_score, 4),
        "dimension_scores": {k: round(v, 4) for k, v in result.dimension_scores.items()},
        "failure_class": failure_class,
        "reasoning": result.reasoning,
        "judge_model": result.judge_model,
    }


# ---------------------------------------------------------------------------
# Provider setup
# ---------------------------------------------------------------------------
_providers: dict[str, object] = {}


def _get_provider(name: str):
    """Lazy-init provider."""
    if name not in _providers:
        if name == "openai":
            from radslice.providers.openai import OpenAIProvider

            _providers[name] = OpenAIProvider()
        elif name == "anthropic":
            from radslice.providers.anthropic import AnthropicProvider

            _providers[name] = AnthropicProvider()
        else:
            raise ValueError(f"Unknown provider: {name}")
    return _providers[name]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze_results(results: list[dict]) -> dict:
    """Compute summary statistics."""
    valid = [r for r in results if "passed" in r]
    passed = [r for r in valid if r["passed"]]
    failed = [r for r in valid if not r["passed"]]
    errors = [r for r in results if "error" in r]

    # Group failures by failure_class
    failure_classes = defaultdict(list)
    for r in failed:
        fc = r.get("failure_class") or "score_below_threshold"
        failure_classes[fc].append(r["task_id"])

    return {
        "total_tasks": len(results),
        "audited": len(valid),
        "errors": len(errors),
        "reference_passes_judge": len(passed),
        "reference_fails_judge": len(failed),
        "solvability_rate": round(len(passed) / len(valid), 4) if valid else 0,
        "failed_task_ids": [r["task_id"] for r in failed],
        "failure_breakdown": dict(failure_classes),
        "error_task_ids": [r["task_id"] for r in errors],
        "mean_score_passed": round(sum(r["weighted_score"] for r in passed) / len(passed), 4)
        if passed
        else 0,
        "mean_score_failed": round(sum(r["weighted_score"] for r in failed) / len(failed), 4)
        if failed
        else 0,
    }


def print_report(results: list[dict], summary: dict) -> None:
    """Print human-readable report."""
    W = 72
    print("=" * W)
    print("  RC1.1 SOLVABILITY AUDIT — REFERENCE SOLUTIONS vs JUDGE")
    print("=" * W)
    print()
    print(f"  Tasks audited:      {summary['audited']}")
    print(f"  Reference passes:   {summary['reference_passes_judge']}")
    print(f"  Reference fails:    {summary['reference_fails_judge']}")
    print(f"  Solvability rate:   {summary['solvability_rate']:.1%}")
    print(f"  Mean score (pass):  {summary['mean_score_passed']:.4f}")
    print(f"  Mean score (fail):  {summary['mean_score_failed']:.4f}")
    print()

    failed = [r for r in results if r.get("passed") is False]
    if failed:
        print("REFERENCE SOLUTION FAILURES (eval defects)")
        print("-" * 60)
        for r in sorted(failed, key=lambda x: x["weighted_score"]):
            print(
                f"  {r['task_id']:12s}  score={r['weighted_score']:.4f}  "
                f"class={r['failure_class'] or '-':1s}  "
                f"{r['reasoning'][:70]}"
            )
        print()

    passed_list = [r for r in results if r.get("passed") is True]
    if passed_list:
        # Show lowest-scoring passes (near threshold)
        near = [r for r in passed_list if r["weighted_score"] < 0.65]
        if near:
            print("NEAR-THRESHOLD PASSES (reference score 0.50-0.65)")
            print("-" * 60)
            for r in sorted(near, key=lambda x: x["weighted_score"]):
                print(
                    f"  {r['task_id']:12s}  score={r['weighted_score']:.4f}  "
                    f"class={r['failure_class'] or '-':1s}"
                )
            print()

    print("FAILURE BREAKDOWN")
    print("-" * 60)
    for fc, task_ids in sorted(summary["failure_breakdown"].items()):
        print(f"  {fc}: {', '.join(task_ids)}")
    print()
    print("=" * W)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main_async():
    import os

    # Load .env if present (check repo root, then lostbench)
    for env_path in [REPO_ROOT / ".env", Path.home() / "lostbench" / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())
            break

    # Get rc1.1 task IDs
    task_ids = sorted(get_rc11_task_ids())
    print(f"Auditing {len(task_ids)} rc1.1 tasks...")

    # Load task YAMLs
    tasks = {}
    for tid in task_ids:
        try:
            tasks[tid] = load_task_yaml(tid)
        except FileNotFoundError:
            print(f"  WARNING: Task YAML not found: {tid}", file=sys.stderr)

    print(f"Loaded {len(tasks)} task YAMLs")

    # Run judge on each reference solution (sequential to avoid rate limits)
    results = []
    for i, (tid, task_data) in enumerate(sorted(tasks.items())):
        print(f"  [{i + 1}/{len(tasks)}] {tid}...", end=" ", flush=True)
        result = await judge_reference_solution(task_data)
        status = "PASS" if result.get("passed") else "FAIL"
        score = result.get("weighted_score", 0)
        fc = result.get("failure_class", "")
        print(f"{status} (score={score:.3f}, class={fc or '-'})")
        results.append(result)

    # Analyze
    summary = analyze_results(results)

    # Write output
    output = {
        "campaign": "rc1.1-solvability-audit",
        "date": "2026-03-07",
        "judge_model": "gpt-5.2",
        "method": "reference_solution fed as model_response to run_judge",
        "summary": summary,
        "per_task": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nOutput written to {OUTPUT_PATH}")

    # Print report
    print()
    print_report(results, summary)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
