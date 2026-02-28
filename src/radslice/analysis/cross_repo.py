"""Cross-repo signal flow: correlate RadSlice findings with LostBench results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CrossRepoFinding:
    """A cross-repo correlation finding."""

    condition_id: str
    radslice_task_ids: list[str]
    lostbench_scenario_ids: list[str]
    classification: str  # both_fail, radslice_only_fail, lostbench_only_fail, both_pass
    radslice_pass_rate: float
    lostbench_pass_rate: float | None  # None if no LostBench data


def build_condition_map(tasks_dir: str | Path) -> dict[str, list[str]]:
    """Build condition_id -> [task_ids] mapping from task YAMLs.

    Args:
        tasks_dir: Directory containing task YAML files (recursive).

    Returns:
        Dict mapping condition_id to list of task IDs.
    """
    tasks_dir = Path(tasks_dir)
    condition_map: dict[str, list[str]] = {}

    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        try:
            with open(yaml_path) as f:
                task = yaml.safe_load(f)
            if not task or "condition_id" not in task or "id" not in task:
                continue
            cid = task["condition_id"]
            if cid not in condition_map:
                condition_map[cid] = []
            condition_map[cid].append(task["id"])
        except Exception:
            continue

    return condition_map


def build_lostbench_map(tasks_dir: str | Path) -> dict[str, list[str]]:
    """Build condition_id -> [lostbench_scenario_ids] from tasks with cross-refs.

    Args:
        tasks_dir: Directory containing task YAML files (recursive).

    Returns:
        Dict mapping condition_id to list of LostBench scenario IDs.
    """
    tasks_dir = Path(tasks_dir)
    lb_map: dict[str, list[str]] = {}

    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        try:
            with open(yaml_path) as f:
                task = yaml.safe_load(f)
            if not task:
                continue
            cid = task.get("condition_id", "")
            lb_id = task.get("lostbench_scenario_id", "")
            if cid and lb_id:
                if cid not in lb_map:
                    lb_map[cid] = []
                if lb_id not in lb_map[cid]:
                    lb_map[cid].append(lb_id)
        except Exception:
            continue

    return lb_map


def _load_radslice_grades(results_dir: str | Path) -> dict[str, list[bool]]:
    """Load RadSlice grades grouped by task_id."""
    grades_path = Path(results_dir) / "grades.jsonl"
    if not grades_path.exists():
        return {}

    task_results: dict[str, list[bool]] = {}
    with open(grades_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            g = json.loads(line)
            tid = g.get("task_id", "")
            if tid:
                if tid not in task_results:
                    task_results[tid] = []
                task_results[tid].append(g.get("passed", False))

    return task_results


def _load_lostbench_grades(results_dir: str | Path) -> dict[str, list[bool]]:
    """Load LostBench grades grouped by scenario_id.

    Reads grades.jsonl from a LostBench results directory.
    No runtime import from LostBench — reads files directly.
    """
    results_dir = Path(results_dir)
    scenario_results: dict[str, list[bool]] = {}

    # Try grades.jsonl first
    grades_path = results_dir / "grades.jsonl"
    if grades_path.exists():
        with open(grades_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                g = json.loads(line)
                sid = g.get("scenario_id", "")
                if sid:
                    if sid not in scenario_results:
                        scenario_results[sid] = []
                    scenario_results[sid].append(g.get("passed", False))

    # Also check individual grade files (LostBench format)
    for grade_file in sorted(results_dir.glob("*_grades.json")):
        try:
            with open(grade_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                for g in data:
                    sid = g.get("scenario_id", "")
                    passed = g.get("passed", g.get("escalation_maintained", False))
                    if sid:
                        if sid not in scenario_results:
                            scenario_results[sid] = []
                        scenario_results[sid].append(passed)
        except Exception:
            continue

    return scenario_results


def correlate_findings(
    radslice_results_dir: str | Path,
    lostbench_results_dir: str | Path | None,
    tasks_dir: str | Path,
) -> list[CrossRepoFinding]:
    """Correlate RadSlice and LostBench findings by condition.

    Args:
        radslice_results_dir: RadSlice results directory with grades.jsonl.
        lostbench_results_dir: LostBench results directory (optional).
        tasks_dir: RadSlice tasks directory for condition/LostBench mapping.

    Returns:
        List of CrossRepoFinding objects.
    """
    condition_map = build_condition_map(tasks_dir)
    lb_map = build_lostbench_map(tasks_dir)

    rs_grades = _load_radslice_grades(radslice_results_dir)

    lb_grades: dict[str, list[bool]] = {}
    if lostbench_results_dir:
        lb_grades = _load_lostbench_grades(lostbench_results_dir)

    findings = []
    for cid, task_ids in sorted(condition_map.items()):
        # RadSlice pass rate for this condition
        rs_results: list[bool] = []
        for tid in task_ids:
            rs_results.extend(rs_grades.get(tid, []))

        rs_pass_rate = sum(rs_results) / len(rs_results) if rs_results else None

        # LostBench pass rate for this condition
        lb_scenario_ids = lb_map.get(cid, [])
        lb_results: list[bool] = []
        for sid in lb_scenario_ids:
            lb_results.extend(lb_grades.get(sid, []))

        lb_pass_rate = sum(lb_results) / len(lb_results) if lb_results else None

        # Skip conditions with no results at all
        if rs_pass_rate is None and lb_pass_rate is None:
            continue

        # Classify
        rs_pass = rs_pass_rate is not None and rs_pass_rate >= 0.5
        lb_pass = lb_pass_rate is not None and lb_pass_rate >= 0.5
        lb_available = lb_pass_rate is not None

        if lb_available:
            if rs_pass and lb_pass:
                classification = "both_pass"
            elif not rs_pass and not lb_pass:
                classification = "both_fail"
            elif not rs_pass and lb_pass:
                classification = "radslice_only_fail"
            else:
                classification = "lostbench_only_fail"
        else:
            classification = "both_pass" if rs_pass else "radslice_only_fail"

        findings.append(
            CrossRepoFinding(
                condition_id=cid,
                radslice_task_ids=task_ids,
                lostbench_scenario_ids=lb_scenario_ids,
                classification=classification,
                radslice_pass_rate=rs_pass_rate if rs_pass_rate is not None else 0.0,
                lostbench_pass_rate=lb_pass_rate,
            )
        )

    return findings


def generate_cross_repo_report(findings: list[CrossRepoFinding]) -> str:
    """Generate markdown report from cross-repo correlation findings."""
    lines = [
        "# Cross-Repo Correlation Report",
        "",
        f"**Conditions analyzed:** {len(findings)}",
        "",
    ]

    # Summary counts
    counts = {"both_pass": 0, "both_fail": 0, "radslice_only_fail": 0, "lostbench_only_fail": 0}
    for f in findings:
        counts[f.classification] += 1

    lines.append("## Classification Summary")
    lines.append("")
    lines.append("| Classification | Count |")
    lines.append("|---------------|-------|")
    for cls, count in counts.items():
        lines.append(f"| {cls} | {count} |")
    lines.append("")

    # Divergent findings (most interesting)
    divergent = [
        f for f in findings if f.classification in ("radslice_only_fail", "lostbench_only_fail")
    ]
    if divergent:
        lines.append("## Divergent Findings (Require Investigation)")
        lines.append("")
        for f in divergent:
            lines.append(f"### {f.condition_id} ({f.classification})")
            lines.append(f"- RadSlice tasks: {', '.join(f.radslice_task_ids)}")
            lines.append(f"- RadSlice pass rate: {f.radslice_pass_rate:.1%}")
            if f.lostbench_scenario_ids:
                lines.append(f"- LostBench scenarios: {', '.join(f.lostbench_scenario_ids)}")
            if f.lostbench_pass_rate is not None:
                lines.append(f"- LostBench pass rate: {f.lostbench_pass_rate:.1%}")
            lines.append("")

    # Both-fail findings
    both_fail = [f for f in findings if f.classification == "both_fail"]
    if both_fail:
        lines.append("## Both-Fail Conditions (Confirmed Weaknesses)")
        lines.append("")
        for f in both_fail:
            lines.append(
                f"- **{f.condition_id}**: "
                f"RS={f.radslice_pass_rate:.1%}, "
                f"LB={f.lostbench_pass_rate:.1%}"
            )
        lines.append("")

    return "\n".join(lines)
