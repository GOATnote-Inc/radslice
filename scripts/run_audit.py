#!/usr/bin/env python3
"""Run a program self-audit: coverage, calibration, risk debt, saturation, governance.

Orchestrates all audit checks and writes an entry to results/audit_log.yaml.

Usage:
    python scripts/run_audit.py --results-dirs results/eval-*
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radslice.analysis.calibration_drift import compute_calibration_drift
from radslice.analysis.saturation import detect_saturation


def _load_grades(results_dir: Path) -> list[dict]:
    """Load grades.jsonl from a results directory."""
    grades_path = results_dir / "grades.jsonl"
    if not grades_path.exists():
        return []
    grades = []
    with open(grades_path) as f:
        for line in f:
            line = line.strip()
            if line:
                grades.append(json.loads(line))
    return grades


def _count_task_yamls(tasks_dir: Path) -> dict[str, int]:
    """Count task YAMLs per modality."""
    counts = {"xray": 0, "ct": 0, "mri": 0, "ultrasound": 0, "total": 0}
    for yaml_path in tasks_dir.rglob("*.yaml"):
        modality = yaml_path.parent.name
        if modality in counts:
            counts[modality] += 1
        counts["total"] += 1
    return counts


def _load_calibration_set(cal_path: Path) -> set[str]:
    """Load calibration set task IDs."""
    if not cal_path.exists():
        return set()
    with open(cal_path) as f:
        data = yaml.safe_load(f) or {}
    return set(data.get("task_ids", []))


def run_audit(
    results_dirs: list[Path],
    tasks_dir: Path = Path("configs/tasks"),
    audit_log_path: Path = Path("results/audit_log.yaml"),
    risk_debt_path: Path = Path("results/risk_debt.yaml"),
    index_path: Path = Path("results/index.yaml"),
    calibration_set_path: Path = Path("configs/calibration/calibration_set.yaml"),
    audit_type: str = "scheduled",
) -> dict:
    """Run all audit checks and write entry to audit_log.yaml.

    Returns the audit entry dict.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Load existing audit log
    if audit_log_path.exists():
        with open(audit_log_path) as f:
            audit_log = yaml.safe_load(f) or {}
    else:
        audit_log = {}
    audits = audit_log.get("audits", [])
    audit_id = f"AUDIT-{len(audits) + 1:03d}"

    # --- Step 1: Coverage Analysis ---
    task_counts = _count_task_yamls(tasks_dir)
    tasks_with_results: set[str] = set()
    all_grades: list[dict] = []

    for rdir in results_dirs:
        rdir = Path(rdir)
        grades = _load_grades(rdir)
        all_grades.extend(grades)
        for g in grades:
            tasks_with_results.add(g.get("task_id", ""))

    total_tasks = task_counts["total"]
    tasks_never_run = total_tasks - len(tasks_with_results)

    # Per-modality coverage
    modality_coverage = {}
    for mod in ("xray", "ct", "mri", "ultrasound"):
        mod_total = task_counts.get(mod, 0)
        mod_prefix = {"xray": "XRAY", "ct": "CT", "mri": "MRI", "ultrasound": "US"}[mod]
        mod_with_results = sum(1 for t in tasks_with_results if t.startswith(mod_prefix))
        modality_coverage[mod] = mod_with_results / mod_total if mod_total > 0 else 0.0

    # --- Step 2: Calibration Drift ---
    cal_set = _load_calibration_set(calibration_set_path)
    drift_report = compute_calibration_drift(all_grades, cal_set if cal_set else None)

    # --- Step 3: Risk Debt ---
    risk_debt = {"open_entries": 0, "critical": 0}
    if risk_debt_path.exists():
        with open(risk_debt_path) as f:
            rd = yaml.safe_load(f) or {}
        entries = rd.get("entries", [])
        open_entries = [e for e in entries if e.get("status") == "open"]
        risk_debt["open_entries"] = len(open_entries)
        risk_debt["critical"] = sum(1 for e in open_entries if e.get("severity") == "critical")

    # --- Step 4: Saturation ---
    sat_report = detect_saturation(results_dirs) if results_dirs else None
    saturation = {
        "saturated_tasks": sat_report.saturated_tasks if sat_report else 0,
        "saturation_rate": sat_report.saturation_rate if sat_report else 0.0,
    }

    # --- Step 5: Governance Review ---
    governance_counter = 0
    if index_path.exists():
        with open(index_path) as f:
            idx = yaml.safe_load(f) or {}
        experiments = idx.get("experiments", [])
        # Count campaigns since last audit
        last_audit_ts = audits[-1]["timestamp"] if audits else "1970-01-01"
        governance_counter = sum(1 for e in experiments if e.get("date", "") > last_audit_ts[:10])

    # --- Build findings ---
    findings = []
    recommendations = []

    if tasks_never_run > total_tasks * 0.5:
        findings.append(
            f"Over 50% of tasks ({tasks_never_run}/{total_tasks}) have never been evaluated"
        )
        recommendations.append("Run full-corpus evaluation for coverage")

    if drift_report.drift_detected:
        findings.append(
            f"Calibration drift detected: kappa={drift_report.layer0_vs_layer2_kappa:.3f}, "
            f"agreement={drift_report.layer0_vs_layer2_agreement:.1%}"
        )
        recommendations.append("Review grading patterns and judge alignment")

    if risk_debt["critical"] > 0:
        findings.append(f"{risk_debt['critical']} critical risk debt entries unresolved")
        recommendations.append("Prioritize Class A failure resolution")

    if saturation["saturation_rate"] > 0.1:
        findings.append(f"Saturation rate {saturation['saturation_rate']:.1%} exceeds 10%")
        recommendations.append("Initiate corpus evolution for saturated tasks")

    # --- Write audit entry ---
    entry = {
        "id": audit_id,
        "timestamp": timestamp,
        "type": audit_type,
        "coverage": {
            "total_tasks": total_tasks,
            "tasks_with_results": len(tasks_with_results),
            "tasks_never_run": tasks_never_run,
            "modality_coverage": modality_coverage,
        },
        "calibration": {
            "kappa": (drift_report.layer0_vs_layer2_kappa if drift_report.total_grades else None),
            "agreement": (
                drift_report.layer0_vs_layer2_agreement if drift_report.total_grades else None
            ),
            "drift_detected": drift_report.drift_detected,
        },
        "saturation": saturation,
        "risk_debt": risk_debt,
        "governance_review_counter": governance_counter,
        "findings": findings,
        "recommendations": recommendations,
    }

    audits.append(entry)
    audit_log["audits"] = audits

    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_log_path, "w") as f:
        yaml.dump(audit_log, f, default_flow_style=False, sort_keys=False)

    return entry


def main():
    parser = argparse.ArgumentParser(description="Run RadSlice program audit")
    parser.add_argument(
        "--results-dirs",
        nargs="+",
        default=[],
        help="Results directories to analyze",
    )
    parser.add_argument(
        "--tasks-dir",
        default="configs/tasks",
        help="Tasks directory",
    )
    parser.add_argument(
        "--type",
        default="scheduled",
        choices=["scheduled", "event-driven"],
        help="Audit type",
    )
    args = parser.parse_args()

    results_dirs = [Path(d) for d in args.results_dirs]
    entry = run_audit(
        results_dirs=results_dirs,
        tasks_dir=Path(args.tasks_dir),
        audit_type=args.type,
    )

    print(f"Audit {entry['id']} completed at {entry['timestamp']}")
    cov = entry["coverage"]
    print(f"  Coverage: {cov['tasks_with_results']}/{cov['total_tasks']} tasks")
    cal = entry["calibration"]
    print(f"  Calibration drift: {'YES' if cal['drift_detected'] else 'No'}")
    sat = entry["saturation"]
    print(f"  Saturation: {sat['saturation_rate']:.1%}")
    rd = entry["risk_debt"]
    print(f"  Risk debt: {rd['open_entries']} open ({rd['critical']} critical)")

    if entry["findings"]:
        print(f"\nFindings ({len(entry['findings'])}):")
        for f in entry["findings"]:
            print(f"  - {f}")

    if entry["recommendations"]:
        print(f"\nRecommendations ({len(entry['recommendations'])}):")
        for r in entry["recommendations"]:
            print(f"  - {r}")


if __name__ == "__main__":
    main()
