"""Suite membership tracking: capability vs regression vs retired."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TaskMembership:
    """Tracking data for a single task's suite membership."""

    suite: str = "capability"  # capability | regression | retired
    consecutive_all_pass: int = 0
    consecutive_any_fail: int = 0
    promoted_date: str | None = None
    retired_date: str | None = None


@dataclass
class SuiteMembership:
    """Full suite membership state."""

    capability: dict[str, int] = field(
        default_factory=lambda: {
            "xray": 0,
            "ct": 0,
            "mri": 0,
            "ultrasound": 0,
            "total": 0,
        }
    )
    regression: dict[str, int] = field(
        default_factory=lambda: {
            "xray": 0,
            "ct": 0,
            "mri": 0,
            "ultrasound": 0,
            "total": 0,
        }
    )
    retired: dict[str, int] = field(
        default_factory=lambda: {
            "xray": 0,
            "ct": 0,
            "mri": 0,
            "ultrasound": 0,
            "total": 0,
        }
    )
    tasks: dict[str, TaskMembership] = field(default_factory=dict)


def _infer_modality(task_id: str) -> str:
    """Infer modality from task ID prefix."""
    prefix = task_id.split("-")[0].lower()
    modality_map = {"xray": "xray", "ct": "ct", "mri": "mri", "us": "ultrasound"}
    return modality_map.get(prefix, "unknown")


def load_suite_membership(path: str | Path) -> SuiteMembership:
    """Load suite membership from YAML."""
    path = Path(path)
    if not path.exists():
        return SuiteMembership()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    membership = SuiteMembership()

    for suite_name in ("capability", "regression", "retired"):
        if suite_name in data and isinstance(data[suite_name], dict):
            setattr(membership, suite_name, data[suite_name])

    if "tasks" in data and isinstance(data["tasks"], dict):
        for task_id, task_data in data["tasks"].items():
            if isinstance(task_data, dict):
                membership.tasks[task_id] = TaskMembership(
                    suite=task_data.get("suite", "capability"),
                    consecutive_all_pass=task_data.get("consecutive_all_pass", 0),
                    consecutive_any_fail=task_data.get("consecutive_any_fail", 0),
                    promoted_date=task_data.get("promoted_date"),
                    retired_date=task_data.get("retired_date"),
                )

    return membership


def save_suite_membership(membership: SuiteMembership, path: str | Path) -> None:
    """Save suite membership to YAML."""
    path = Path(path)

    tasks_dict: dict[str, dict[str, Any]] = {}
    for task_id, tm in sorted(membership.tasks.items()):
        tasks_dict[task_id] = {
            "suite": tm.suite,
            "consecutive_all_pass": tm.consecutive_all_pass,
            "consecutive_any_fail": tm.consecutive_any_fail,
            "promoted_date": tm.promoted_date,
            "retired_date": tm.retired_date,
        }

    data = {
        "capability": membership.capability,
        "regression": membership.regression,
        "retired": membership.retired,
        "tasks": tasks_dict,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _recount_suites(membership: SuiteMembership) -> None:
    """Recompute per-modality counts from task data."""
    for suite_name in ("capability", "regression", "retired"):
        counts = {"xray": 0, "ct": 0, "mri": 0, "ultrasound": 0, "total": 0}
        for task_id, tm in membership.tasks.items():
            if tm.suite == suite_name:
                mod = _infer_modality(task_id)
                if mod in counts:
                    counts[mod] += 1
                counts["total"] += 1
        setattr(membership, suite_name, counts)


def propose_promotions(
    grades: list[dict],
    membership: SuiteMembership,
    min_models_broken: int = 2,
) -> list[str]:
    """Propose tasks for promotion to regression suite.

    A task is promoted if it discriminates between models:
    at least min_models_broken models fail while others pass.

    Args:
        grades: List of grade dicts with task_id, model, passed fields.
        membership: Current suite membership.
        min_models_broken: Minimum models that must fail (while others pass).

    Returns:
        List of task IDs proposed for promotion.
    """
    # Group pass/fail by (task_id, model)
    task_model_results: dict[str, dict[str, list[bool]]] = {}
    for g in grades:
        task_id = g["task_id"]
        model = g["model"]
        if task_id not in task_model_results:
            task_model_results[task_id] = {}
        if model not in task_model_results[task_id]:
            task_model_results[task_id][model] = []
        task_model_results[task_id][model].append(g.get("passed", False))

    proposals = []
    for task_id, model_results in task_model_results.items():
        # Skip if already in regression
        tm = membership.tasks.get(task_id)
        if tm and tm.suite == "regression":
            continue

        # Check discrimination: some models pass, some fail
        model_pass_rates = {}
        for model, trials in model_results.items():
            model_pass_rates[model] = sum(trials) / len(trials) if trials else 0.0

        passing_models = sum(1 for r in model_pass_rates.values() if r >= 0.5)
        failing_models = sum(1 for r in model_pass_rates.values() if r < 0.5)

        if failing_models >= min_models_broken and passing_models >= 1:
            proposals.append(task_id)

    return sorted(proposals)


def propose_retirements(
    membership: SuiteMembership,
    max_consecutive_passes: int = 5,
) -> list[str]:
    """Propose tasks for retirement from capability suite.

    Tasks that have passed for all models across max_consecutive_passes
    consecutive runs are flagged for evolution/retirement.

    Returns:
        List of task IDs proposed for retirement.
    """
    proposals = []
    for task_id, tm in membership.tasks.items():
        if tm.suite == "capability" and tm.consecutive_all_pass >= max_consecutive_passes:
            proposals.append(task_id)
    return sorted(proposals)


def update_tracking(
    membership: SuiteMembership,
    grades: list[dict],
) -> None:
    """Update consecutive pass/fail counters from a new run's grades.

    Modifies membership in place.

    Args:
        membership: Current suite membership state.
        grades: Grade dicts from the latest run.
    """
    # Group by task_id
    task_results: dict[str, list[bool]] = {}
    for g in grades:
        task_id = g["task_id"]
        if task_id not in task_results:
            task_results[task_id] = []
        task_results[task_id].append(g.get("passed", False))

    for task_id, results in task_results.items():
        if task_id not in membership.tasks:
            membership.tasks[task_id] = TaskMembership()

        tm = membership.tasks[task_id]
        all_passed = all(results)

        if all_passed:
            tm.consecutive_all_pass += 1
            tm.consecutive_any_fail = 0
        else:
            tm.consecutive_any_fail += 1
            tm.consecutive_all_pass = 0


def apply_promotion(
    membership: SuiteMembership,
    task_id: str,
) -> None:
    """Promote a task from capability to regression suite."""
    if task_id not in membership.tasks:
        membership.tasks[task_id] = TaskMembership()
    tm = membership.tasks[task_id]
    tm.suite = "regression"
    tm.promoted_date = datetime.now(timezone.utc).isoformat()
    _recount_suites(membership)


def apply_retirement(
    membership: SuiteMembership,
    task_id: str,
) -> None:
    """Retire a task from capability suite."""
    if task_id not in membership.tasks:
        membership.tasks[task_id] = TaskMembership()
    tm = membership.tasks[task_id]
    tm.suite = "retired"
    tm.retired_date = datetime.now(timezone.utc).isoformat()
    _recount_suites(membership)
