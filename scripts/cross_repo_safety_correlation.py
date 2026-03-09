#!/usr/bin/env python3
"""Cross-repo clinical safety correlation: RadSlice rc1.1 × LostBench.

Correlates RadSlice image interpretation results with LostBench text-based
clinical reasoning results on the same OpenEM conditions. Produces findings
that no other radiology benchmark can: cross-modal clinical safety analysis.

Usage:
    python scripts/cross_repo_safety_correlation.py \
        --radslice-gpt results/eval-20260307-gpt52-rc11 \
        --radslice-opus results/eval-20260307-opus46-rc11 \
        --lostbench-gpt /path/to/lostbench/results/campaign-regression-2026-02-28 \
        --lostbench-opus /path/to/lostbench/results/campaign-regression-opus-baseline-2026-02-28 \
        --tasks-dir configs/tasks \
        --output results/cross-repo-correlation-rc11.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass
class PerModelCorrelation:
    """Cross-repo correlation for a single model on a single condition."""

    model: str
    condition_id: str
    condition_name: str
    radslice_task_id: str
    lostbench_scenario_id: str
    radslice_pass_rate: float
    radslice_trials: int
    lostbench_passed: bool
    classification: str  # both_fail, radslice_only_fail, lostbench_only_fail, both_pass
    modality: str


@dataclass
class CorrelationSummary:
    """Summary of cross-repo correlation findings."""

    total_cross_refs: int
    models_analyzed: list[str]
    per_model: dict[str, dict] = field(default_factory=dict)
    confirmed_blind_spots: list[dict] = field(default_factory=list)
    imaging_specific_gaps: list[dict] = field(default_factory=list)
    reasoning_specific_gaps: list[dict] = field(default_factory=list)
    cross_modal_strengths: list[dict] = field(default_factory=list)
    per_correlation: list[dict] = field(default_factory=list)


def load_radslice_grades(results_dir: Path) -> dict[str, list[dict]]:
    """Load RadSlice grades grouped by task_id."""
    grades_path = results_dir / "grades.jsonl"
    task_grades: dict[str, list[dict]] = {}
    with open(grades_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            g = json.loads(line)
            tid = g["task_id"]
            task_grades.setdefault(tid, []).append(g)
    return task_grades


def load_lostbench_ceis(results_dir: Path) -> dict[str, dict]:
    """Load LostBench CEIS results indexed by scenario_id."""
    ceis_path = results_dir / "ceis_results.json"
    with open(ceis_path) as f:
        data = json.load(f)
    return {c["scenario_id"]: c for c in data["conditions"]}


def load_task_crossrefs(tasks_dir: Path) -> list[dict]:
    """Load task YAMLs that have lostbench_scenario_id cross-refs."""
    crossrefs = []
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        try:
            with open(yaml_path) as f:
                task = yaml.safe_load(f)
            if not task:
                continue
            lb_id = task.get("lostbench_scenario_id", "")
            if lb_id:
                crossrefs.append(
                    {
                        "task_id": task["id"],
                        "condition_id": task.get("condition_id", ""),
                        "condition_name": task.get("name", task.get("condition", "")),
                        "lostbench_scenario_id": lb_id,
                        "modality": task.get("modality", "unknown"),
                    }
                )
        except Exception:
            continue
    return crossrefs


def correlate(
    rs_grades: dict[str, list[dict]],
    lb_conditions: dict[str, dict],
    crossrefs: list[dict],
    model_name: str,
) -> list[PerModelCorrelation]:
    """Correlate RadSlice and LostBench results for one model."""
    results = []
    for xref in crossrefs:
        tid = xref["task_id"]
        lb_id = xref["lostbench_scenario_id"]

        # RadSlice pass rate
        grades = rs_grades.get(tid, [])
        if not grades:
            continue
        rs_passed = sum(1 for g in grades if g.get("passed"))
        rs_pass_rate = rs_passed / len(grades)

        # LostBench result
        lb_cond = lb_conditions.get(lb_id)
        if lb_cond is None:
            continue
        lb_passed = lb_cond["passed"]

        # Classify (RS uses 0.5 threshold, LB uses binary pass/fail)
        rs_pass = rs_pass_rate >= 0.5
        if rs_pass and lb_passed:
            classification = "both_pass"
        elif not rs_pass and not lb_passed:
            classification = "both_fail"
        elif not rs_pass and lb_passed:
            classification = "radslice_only_fail"
        else:
            classification = "lostbench_only_fail"

        results.append(
            PerModelCorrelation(
                model=model_name,
                condition_id=xref["condition_id"],
                condition_name=xref["condition_name"],
                radslice_task_id=tid,
                lostbench_scenario_id=lb_id,
                radslice_pass_rate=rs_pass_rate,
                radslice_trials=len(grades),
                lostbench_passed=lb_passed,
                classification=classification,
                modality=xref["modality"],
            )
        )
    return results


def build_summary(
    gpt_correlations: list[PerModelCorrelation],
    opus_correlations: list[PerModelCorrelation],
) -> CorrelationSummary:
    """Build summary from per-model correlations."""
    all_corrs = gpt_correlations + opus_correlations
    summary = CorrelationSummary(
        total_cross_refs=len(set(c.radslice_task_id for c in all_corrs)),
        models_analyzed=["gpt-5.2", "claude-opus-4-6"],
    )

    for model_name, corrs in [
        ("gpt-5.2", gpt_correlations),
        ("claude-opus-4-6", opus_correlations),
    ]:
        counts = {"both_fail": 0, "radslice_only_fail": 0, "lostbench_only_fail": 0, "both_pass": 0}
        for c in corrs:
            counts[c.classification] += 1
        summary.per_model[model_name] = {
            "n_correlations": len(corrs),
            "classification_counts": counts,
        }

    # Find confirmed blind spots (both_fail for any model)
    for c in all_corrs:
        entry = asdict(c)
        if c.classification == "both_fail":
            summary.confirmed_blind_spots.append(entry)
        elif c.classification == "radslice_only_fail":
            summary.imaging_specific_gaps.append(entry)
        elif c.classification == "lostbench_only_fail":
            summary.reasoning_specific_gaps.append(entry)
        else:
            summary.cross_modal_strengths.append(entry)

    summary.per_correlation = [asdict(c) for c in all_corrs]
    return summary


def generate_markdown(summary: CorrelationSummary) -> str:
    """Generate markdown report from correlation summary."""
    lines = [
        "# Cross-Repo Clinical Safety Correlation: RadSlice rc1.1 × LostBench",
        "",
        "Cross-modal correlation between RadSlice (image interpretation) and LostBench",
        "(text-based clinical reasoning) on shared OpenEM conditions.",
        "",
        f"**Tasks with cross-references:** {summary.total_cross_refs}",
        f"**Models analyzed:** {', '.join(summary.models_analyzed)}",
        "",
        "## Classification Summary",
        "",
        "| Model | Both Fail | RS Only Fail | LB Only Fail | Both Pass | Total |",
        "|-------|-----------|-------------|-------------|-----------|-------|",
    ]

    for model, data in summary.per_model.items():
        c = data["classification_counts"]
        lines.append(
            f"| {model} | {c['both_fail']} | {c['radslice_only_fail']} | "
            f"{c['lostbench_only_fail']} | {c['both_pass']} | {data['n_correlations']} |"
        )
    lines.append("")

    # Confirmed blind spots
    if summary.confirmed_blind_spots:
        lines.append("## Confirmed Blind Spots (Both Fail)")
        lines.append("")
        lines.append(
            "These conditions fail in BOTH image interpretation AND text-based clinical reasoning "
            "— confirmed model capability gaps."
        )
        lines.append("")
        lines.append("| Model | Condition | RS Task | RS Pass Rate | LB Scenario | Modality |")
        lines.append("|-------|-----------|---------|-------------|-------------|----------|")
        for c in summary.confirmed_blind_spots:
            lines.append(
                f"| {c['model']} | {c['condition_name']} | {c['radslice_task_id']} | "
                f"{c['radslice_pass_rate']:.0%} | {c['lostbench_scenario_id']} | {c['modality']} |"
            )
        lines.append("")

    # Imaging-specific gaps
    if summary.imaging_specific_gaps:
        lines.append("## Imaging-Specific Gaps (RadSlice Only Fail)")
        lines.append("")
        lines.append(
            "Model reasons correctly in text but fails image interpretation "
            "— visual perception gap."
        )
        lines.append("")
        lines.append("| Model | Condition | RS Task | RS Pass Rate | LB Scenario | Modality |")
        lines.append("|-------|-----------|---------|-------------|-------------|----------|")
        for c in summary.imaging_specific_gaps:
            lines.append(
                f"| {c['model']} | {c['condition_name']} | {c['radslice_task_id']} | "
                f"{c['radslice_pass_rate']:.0%} | {c['lostbench_scenario_id']} | {c['modality']} |"
            )
        lines.append("")

    # Reasoning-specific gaps
    if summary.reasoning_specific_gaps:
        lines.append("## Reasoning-Specific Gaps (LostBench Only Fail)")
        lines.append("")
        lines.append(
            "Model interprets the image correctly but fails text-based clinical reasoning."
        )
        lines.append("")
        lines.append("| Model | Condition | RS Task | RS Pass Rate | LB Scenario | Modality |")
        lines.append("|-------|-----------|---------|-------------|-------------|----------|")
        for c in summary.reasoning_specific_gaps:
            lines.append(
                f"| {c['model']} | {c['condition_name']} | {c['radslice_task_id']} | "
                f"{c['radslice_pass_rate']:.0%} | {c['lostbench_scenario_id']} | {c['modality']} |"
            )
        lines.append("")

    # Cross-model asymmetries
    lines.append("## Cross-Model Asymmetries")
    lines.append("")

    # Group by task to find where models diverge
    by_task: dict[str, dict[str, dict]] = {}
    for c in summary.per_correlation:
        by_task.setdefault(c["radslice_task_id"], {})[c["model"]] = c

    asymmetries = []
    for tid, models in sorted(by_task.items()):
        if len(models) == 2:
            m1, m2 = list(models.values())
            if m1["classification"] != m2["classification"]:
                asymmetries.append((tid, m1, m2))

    if asymmetries:
        lines.append("Tasks where GPT-5.2 and Opus 4.6 show different cross-modal patterns:")
        lines.append("")
        lines.append("| Task | Condition | GPT Class | Opus Class | GPT RS | Opus RS |")
        lines.append("|------|-----------|-----------|-----------|--------|---------|")
        for tid, m1, m2 in asymmetries:
            gpt = m1 if m1["model"] == "gpt-5.2" else m2
            opus = m2 if m1["model"] == "gpt-5.2" else m1
            lines.append(
                f"| {tid} | {gpt['condition_name']} | {gpt['classification']} | "
                f"{opus['classification']} | {gpt['radslice_pass_rate']:.0%} | "
                f"{opus['radslice_pass_rate']:.0%} |"
            )
        lines.append("")
    else:
        lines.append("No cross-model asymmetries found.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Cross-repo clinical safety correlation")
    parser.add_argument("--radslice-gpt", required=True, type=Path)
    parser.add_argument("--radslice-opus", required=True, type=Path)
    parser.add_argument("--lostbench-gpt", required=True, type=Path)
    parser.add_argument("--lostbench-opus", required=True, type=Path)
    parser.add_argument("--tasks-dir", default="configs/tasks", type=Path)
    parser.add_argument("--output", default="results/cross-repo-correlation-rc11.json", type=Path)
    args = parser.parse_args()

    # Load data
    crossrefs = load_task_crossrefs(args.tasks_dir)
    print(f"Found {len(crossrefs)} tasks with LostBench cross-references")

    rs_gpt = load_radslice_grades(args.radslice_gpt)
    rs_opus = load_radslice_grades(args.radslice_opus)
    lb_gpt = load_lostbench_ceis(args.lostbench_gpt)
    lb_opus = load_lostbench_ceis(args.lostbench_opus)

    print(f"RadSlice GPT tasks: {len(rs_gpt)}, Opus tasks: {len(rs_opus)}")
    print(f"LostBench GPT scenarios: {len(lb_gpt)}, Opus scenarios: {len(lb_opus)}")

    # Filter crossrefs to only rc1.1 tasks
    rc11_task_ids = set(rs_gpt.keys()) | set(rs_opus.keys())
    rc11_crossrefs = [x for x in crossrefs if x["task_id"] in rc11_task_ids]
    print(f"RC1.1 tasks with cross-references: {len(rc11_crossrefs)}")

    # Correlate per model
    gpt_corrs = correlate(rs_gpt, lb_gpt, rc11_crossrefs, "gpt-5.2")
    opus_corrs = correlate(rs_opus, lb_opus, rc11_crossrefs, "claude-opus-4-6")
    print(f"GPT correlations: {len(gpt_corrs)}, Opus correlations: {len(opus_corrs)}")

    # Build summary
    summary = build_summary(gpt_corrs, opus_corrs)

    # Write JSON
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(asdict(summary), f, indent=2)
    print(f"Wrote {args.output}")

    # Write markdown
    md_path = args.output.with_suffix(".md")
    with open(md_path, "w") as f:
        f.write(generate_markdown(summary))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
