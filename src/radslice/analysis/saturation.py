"""Saturation detection: identify tasks that no longer discriminate between models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from radslice.scoring import pass_pow_k


@dataclass(frozen=True)
class TaskSaturation:
    """Saturation status for a single task."""

    task_id: str
    models_saturated: dict[str, bool]  # model -> saturated?
    pass_pow_k_by_model: dict[str, float]  # model -> pass^k rate across runs
    consecutive_all_pass: int
    saturated: bool  # True if pass@5 > threshold for ALL models for min_consecutive_runs


@dataclass(frozen=True)
class CorpusSaturationReport:
    """Saturation report across the full corpus."""

    total_tasks: int
    saturated_tasks: int
    saturation_rate: float
    per_modality: dict[str, dict[str, int]]  # modality -> {total, saturated, rate}
    per_difficulty: dict[str, dict[str, int]]  # difficulty -> {total, saturated}
    task_details: list[TaskSaturation]
    needs_evolution: list[str]  # task IDs needing harder variants
    threshold: float
    min_consecutive_runs: int


def _infer_modality(task_id: str) -> str:
    """Infer modality from task ID prefix."""
    prefix = task_id.split("-")[0].lower()
    modality_map = {"xray": "xray", "ct": "ct", "mri": "mri", "us": "ultrasound"}
    return modality_map.get(prefix, "unknown")


def _load_grades_from_dir(results_dir: str | Path) -> list[dict]:
    """Load grades.jsonl from a results directory."""
    grades_path = Path(results_dir) / "grades.jsonl"
    if not grades_path.exists():
        return []
    grades = []
    with open(grades_path) as f:
        for line in f:
            line = line.strip()
            if line:
                grades.append(json.loads(line))
    return grades


def detect_saturation(
    results_dirs: list[str | Path],
    threshold: float = 0.95,
    min_consecutive_runs: int = 3,
) -> CorpusSaturationReport:
    """Detect saturated tasks across multiple evaluation runs.

    A task is saturated when pass^k > threshold for ALL models
    across min_consecutive_runs consecutive runs.

    Args:
        results_dirs: Ordered list of result directories (oldest first).
        threshold: pass^k threshold for saturation (default 0.95).
        min_consecutive_runs: Minimum consecutive runs above threshold.

    Returns:
        CorpusSaturationReport with per-task and aggregate saturation data.
    """
    # Collect all grades grouped by (task_id, model) per run
    # runs[run_idx][(task_id, model)] -> list[bool]
    runs: list[dict[tuple[str, str], list[bool]]] = []

    for rdir in results_dirs:
        grades = _load_grades_from_dir(rdir)
        run_data: dict[tuple[str, str], list[bool]] = {}
        for g in grades:
            key = (g["task_id"], g["model"])
            if key not in run_data:
                run_data[key] = []
            run_data[key].append(g.get("passed", False))
        runs.append(run_data)

    if not runs:
        return CorpusSaturationReport(
            total_tasks=0,
            saturated_tasks=0,
            saturation_rate=0.0,
            per_modality={},
            per_difficulty={},
            task_details=[],
            needs_evolution=[],
            threshold=threshold,
            min_consecutive_runs=min_consecutive_runs,
        )

    # Gather all unique task IDs and models
    all_keys: set[tuple[str, str]] = set()
    for run_data in runs:
        all_keys.update(run_data.keys())

    all_task_ids = sorted({k[0] for k in all_keys})
    all_models = sorted({k[1] for k in all_keys})

    # For each task, compute per-model pass^k across runs
    task_details = []
    saturated_ids = []

    for task_id in all_task_ids:
        models_saturated: dict[str, bool] = {}
        pass_pow_k_by_model: dict[str, float] = {}

        for model in all_models:
            # Count consecutive recent runs where pass^k holds
            consecutive = 0
            total_trials_all_runs: list[bool] = []

            for run_data in reversed(runs):  # most recent first
                trials = run_data.get((task_id, model), [])
                if trials and pass_pow_k(trials):
                    consecutive += 1
                else:
                    break

            # Aggregate pass rate across all runs
            for run_data in runs:
                trials = run_data.get((task_id, model), [])
                total_trials_all_runs.extend(trials)

            if total_trials_all_runs:
                successes = sum(total_trials_all_runs)
                n = len(total_trials_all_runs)
                rate = successes / n
            else:
                rate = 0.0
                consecutive = 0

            models_saturated[model] = consecutive >= min_consecutive_runs and rate >= threshold
            pass_pow_k_by_model[model] = rate

        # Task is saturated if ALL models are saturated
        all_saturated = bool(models_saturated) and all(models_saturated.values())

        # Count consecutive runs where ALL models pass all trials
        consec = 0
        for run_data in reversed(runs):
            all_pass_this_run = True
            for model in all_models:
                trials = run_data.get((task_id, model), [])
                if not trials or not pass_pow_k(trials):
                    all_pass_this_run = False
                    break
            if all_pass_this_run:
                consec += 1
            else:
                break

        ts = TaskSaturation(
            task_id=task_id,
            models_saturated=models_saturated,
            pass_pow_k_by_model=pass_pow_k_by_model,
            consecutive_all_pass=consec,
            saturated=all_saturated,
        )
        task_details.append(ts)

        if all_saturated:
            saturated_ids.append(task_id)

    # Per-modality breakdown
    per_modality: dict[str, dict[str, int]] = {}
    for ts in task_details:
        mod = _infer_modality(ts.task_id)
        if mod not in per_modality:
            per_modality[mod] = {"total": 0, "saturated": 0}
        per_modality[mod]["total"] += 1
        if ts.saturated:
            per_modality[mod]["saturated"] += 1

    total_tasks = len(all_task_ids)
    saturated_count = len(saturated_ids)

    return CorpusSaturationReport(
        total_tasks=total_tasks,
        saturated_tasks=saturated_count,
        saturation_rate=saturated_count / total_tasks if total_tasks else 0.0,
        per_modality=per_modality,
        per_difficulty={},  # populated when task metadata available
        task_details=task_details,
        needs_evolution=saturated_ids,
        threshold=threshold,
        min_consecutive_runs=min_consecutive_runs,
    )


def format_saturation_report(report: CorpusSaturationReport) -> str:
    """Format saturation report as markdown."""
    lines = [
        "# Corpus Saturation Report",
        "",
        f"- **Total tasks:** {report.total_tasks}",
        f"- **Saturated tasks:** {report.saturated_tasks}",
        f"- **Saturation rate:** {report.saturation_rate:.1%}",
        f"- **Threshold:** pass^k > {report.threshold}",
        f"- **Min consecutive runs:** {report.min_consecutive_runs}",
        "",
    ]

    if report.per_modality:
        lines.append("## Per-Modality Breakdown")
        lines.append("")
        lines.append("| Modality | Total | Saturated | Rate |")
        lines.append("|----------|-------|-----------|------|")
        for mod, data in sorted(report.per_modality.items()):
            total = data["total"]
            sat = data["saturated"]
            rate = sat / total if total else 0.0
            lines.append(f"| {mod} | {total} | {sat} | {rate:.1%} |")
        lines.append("")

    if report.needs_evolution:
        lines.append("## Tasks Needing Evolution")
        lines.append("")
        for tid in report.needs_evolution:
            lines.append(f"- {tid}")
        lines.append("")

    return "\n".join(lines)
