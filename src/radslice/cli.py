"""Click CLI: run, grade, analyze, report, corpus validate/download."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click

from radslice import __version__

logger = logging.getLogger("radslice")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )


@click.group()
@click.version_option(__version__, prog_name="radslice")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """RadSlice: Multimodal Radiology LLM Benchmark."""
    _setup_logging(verbose)


# --- run ---


@main.command()
@click.option("--matrix", type=click.Path(exists=True), help="Matrix config YAML")
@click.option("--tasks-dir", default="configs/tasks", help="Tasks directory")
@click.option("--model", help="Single model name to run")
@click.option("--provider", type=click.Choice(["openai", "anthropic", "google"]))
@click.option("--model-id", help="Model ID (e.g., gpt-5.2)")
@click.option("--n-trials", default=3, type=int, help="Trials per task")
@click.option("--output-dir", default="results/latest", help="Output directory")
@click.option("--resume/--no-resume", default=False, help="Resume from checkpoint")
@click.option("--cache/--no-cache", default=True, help="Enable response caching")
@click.option("--pattern-only", is_flag=True, help="Skip LLM judge, patterns only")
@click.option("--judge-model", default="gpt-5.2", help="Judge model")
@click.option("--modality", help="Filter to one modality")
@click.option("--max-concurrency", default=5, type=int, help="Max parallel API calls")
@click.option("--corpus-dir", default="corpus", help="Corpus directory")
def run(
    matrix,
    tasks_dir,
    model,
    provider,
    model_id,
    n_trials,
    output_dir,
    resume,
    cache,
    pattern_only,
    judge_model,
    modality,
    max_concurrency,
    corpus_dir,
):
    """Execute evaluation matrix."""
    from radslice.cache import ResponseCache
    from radslice.executor import MatrixConfig, MatrixExecutor
    from radslice.grading.grader import RubricGrader
    from radslice.providers.cached import CachedProvider

    # Build config
    if matrix:
        config = MatrixConfig.from_yaml(matrix)
    elif model and provider and model_id:
        config = MatrixConfig(
            tasks_dir=tasks_dir,
            models=[{"name": model, "provider": provider, "model_id": model_id}],
            n_trials=n_trials,
            max_concurrency=max_concurrency,
            modality_filter=modality,
        )
    else:
        raise click.UsageError("Provide --matrix or (--model + --provider + --model-id)")

    # Print configuration
    click.echo("=" * 60, err=True)
    click.echo(f"RadSlice v{__version__} — Evaluation Run", err=True)
    click.echo(f"  Tasks dir: {config.tasks_dir}", err=True)
    click.echo(f"  Models: {[m['name'] for m in config.models]}", err=True)
    click.echo(f"  Trials: {config.n_trials}", err=True)
    click.echo(f"  Output: {output_dir}", err=True)
    click.echo(f"  Cache: {cache}", err=True)
    click.echo(f"  Pattern-only: {pattern_only}", err=True)
    click.echo(f"  Judge: {judge_model}", err=True)
    click.echo("=" * 60, err=True)

    # Build providers
    providers = _build_providers(config.models)

    if cache:
        response_cache = ResponseCache(output_dir)
        providers = {name: CachedProvider(p, response_cache) for name, p in providers.items()}

    # Build grader
    judge_provider = None
    if not pattern_only:
        judge_provider = _get_judge_provider(judge_model, providers)

    grader = RubricGrader(
        judge_provider=judge_provider,
        judge_model=judge_model,
        pattern_only=pattern_only,
    )

    executor = MatrixExecutor(
        providers=providers,
        grader=grader,
        corpus_dir=corpus_dir,
        output_dir=output_dir,
        resume=resume,
    )

    result = asyncio.run(executor.run(config))

    # Summary
    click.echo(f"\nResults: {len(result.grades)} grades, {len(result.errors)} errors")
    if result.grades:
        passed = sum(1 for g in result.grades if g.passed)
        click.echo(f"Pass rate: {passed}/{len(result.grades)} ({passed / len(result.grades):.1%})")

    if cache:
        for p in providers.values():
            if hasattr(p, "cache_stats"):
                click.echo(f"Cache stats: {p.cache_stats}", err=True)


# --- grade ---


@main.command()
@click.option("--results", required=True, type=click.Path(exists=True), help="Results directory")
@click.option("--judge-model", default="gpt-5.2", help="Judge model for re-grading")
@click.option("--pattern-only", is_flag=True, help="Pattern-only re-grading")
@click.option("--output", help="Output file (default: same dir)")
def grade(results, judge_model, pattern_only, output):
    """Re-grade existing results with different judge/settings."""
    from radslice.grading.grader import RubricGrader
    from radslice.transcript import load_transcript

    results_path = Path(results)
    transcript_path = results_path / "transcripts.jsonl"
    if not transcript_path.exists():
        raise click.UsageError(f"No transcripts.jsonl in {results}")

    transcripts = load_transcript(transcript_path)
    click.echo(f"Loaded {len(transcripts)} transcripts")

    grader = RubricGrader(pattern_only=True)  # Always pattern-only for offline re-grade

    # Load tasks from config
    tasks_dir = results_path / "tasks_dir.txt"
    if tasks_dir.exists():
        task_dir_path = tasks_dir.read_text().strip()
    else:
        task_dir_path = "configs/tasks"

    click.echo(f"Re-grading with pattern-only={pattern_only}, judge={judge_model}")

    output_path = Path(output) if output else results_path / "grades_regraded.jsonl"
    asyncio.run(_regrade(grader, transcripts, task_dir_path, output_path))
    click.echo(f"Re-graded results written to {output_path}")


async def _regrade(grader, transcripts, tasks_dir, output_path):
    from radslice.task import load_tasks_from_dir

    tasks_by_id = {t.id: t for t in load_tasks_from_dir(tasks_dir)}

    with open(output_path, "w") as f:
        for t in transcripts:
            task = tasks_by_id.get(t.task_id)
            if not task:
                continue
            grade = await grader.grade(task, t.response, t.model, t.trial)
            f.write(json.dumps(grade.to_dict()) + "\n")


# --- analyze ---


@main.command()
@click.option("--results", required=True, type=click.Path(exists=True), help="Results directory")
@click.option("--per-modality", is_flag=True, help="Per-modality breakdown")
@click.option("--per-anatomy", is_flag=True, help="Per-anatomy breakdown")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json", "csv"]), default="markdown")
def analyze(results, per_modality, per_anatomy, fmt):
    """Analyze evaluation results."""
    from radslice.analysis.per_anatomy import anatomy_breakdown
    from radslice.analysis.per_modality import modality_breakdown
    from radslice.analysis.report import format_report

    grades = _load_grades(results)
    if fmt == "markdown":
        click.echo(f"Loaded {len(grades)} grades", err=True)

    report_data: dict = {"total_grades": len(grades)}

    if per_modality or (not per_modality and not per_anatomy):
        report_data["by_modality"] = modality_breakdown(grades)

    if per_anatomy:
        report_data["by_anatomy"] = anatomy_breakdown(grades)

    output = format_report(report_data, fmt)
    click.echo(output)


# --- report ---


@main.command()
@click.option("--results", required=True, type=click.Path(exists=True))
@click.option("--compare", type=click.Path(exists=True), help="Compare with another run")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def report(results, compare, fmt):
    """Generate evaluation report, optionally comparing two runs."""
    from radslice.analysis.regression import detect_regression
    from radslice.analysis.report import format_report

    grades_a = _load_grades(results)
    report_data: dict = {
        "run_a": results,
        "total_grades": len(grades_a),
    }

    if compare:
        grades_b = _load_grades(compare)
        regression = detect_regression(grades_a, grades_b)
        report_data["comparison"] = {
            "run_b": compare,
            "total_grades_b": len(grades_b),
            "regression": regression,
        }

    output = format_report(report_data, fmt)
    click.echo(output)


# --- corpus ---


@main.group()
def corpus():
    """Corpus management commands."""
    pass


@corpus.command("validate")
@click.option("--tasks-dir", default="configs/tasks", help="Tasks directory")
def corpus_validate(tasks_dir):
    """Validate all task YAMLs."""
    from radslice.task import TaskValidationError, load_task

    tasks_path = Path(tasks_dir)
    if not tasks_path.exists():
        raise click.UsageError(f"Tasks directory not found: {tasks_dir}")

    yamls = sorted(tasks_path.rglob("*.yaml"))
    click.echo(f"Validating {len(yamls)} task YAMLs...")

    errors = []
    valid = 0
    for path in yamls:
        try:
            load_task(path)
            valid += 1
        except (TaskValidationError, Exception) as exc:
            errors.append((str(path), str(exc)))

    click.echo(f"Valid: {valid}, Errors: {len(errors)}")
    for path, err in errors:
        click.echo(f"  ERROR {path}: {err}", err=True)

    if errors:
        sys.exit(1)


@corpus.command("download")
@click.option("--manifest", default="corpus/manifest.yaml", help="Manifest path")
@click.option("--output-dir", default="corpus/images", help="Image output directory")
def corpus_download(manifest, output_dir):
    """Download corpus images from sources."""
    click.echo(f"Downloading images from {manifest} to {output_dir}")
    click.echo("(Not yet implemented — requires dataset-specific downloaders)")


# --- saturation ---


@main.command()
@click.option(
    "--results-dirs",
    required=True,
    multiple=True,
    type=click.Path(exists=True),
    help="Results directories (ordered oldest first)",
)
@click.option("--threshold", default=0.95, type=float, help="pass^k saturation threshold")
@click.option("--min-runs", default=3, type=int, help="Min consecutive runs above threshold")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def saturation(results_dirs, threshold, min_runs, fmt):
    """Detect saturated tasks across evaluation runs."""
    from radslice.analysis.saturation import detect_saturation, format_saturation_report

    report = detect_saturation(
        results_dirs=list(results_dirs),
        threshold=threshold,
        min_consecutive_runs=min_runs,
    )

    if fmt == "json":
        import dataclasses

        click.echo(json.dumps(dataclasses.asdict(report), indent=2, default=str))
    else:
        click.echo(format_saturation_report(report))


# --- suite-update ---


@main.command("suite-update")
@click.option("--results", required=True, type=click.Path(exists=True), help="Results directory")
@click.option(
    "--membership",
    default="results/suite_membership.yaml",
    help="Suite membership YAML",
)
@click.option("--min-models-broken", default=2, type=int, help="Min models broken for promotion")
@click.option("--max-consecutive-passes", default=5, type=int, help="Max passes for retirement")
@click.option("--apply/--dry-run", default=False, help="Apply changes or just report")
def suite_update(results, membership, min_models_broken, max_consecutive_passes, apply):
    """Update suite membership based on evaluation results."""
    from radslice.analysis.suite_tracker import (
        apply_promotion,
        apply_retirement,
        load_suite_membership,
        propose_promotions,
        propose_retirements,
        save_suite_membership,
        update_tracking,
    )

    grades = _load_grades(results)
    if not grades:
        click.echo("No grades found.", err=True)
        return

    mem = load_suite_membership(membership)
    update_tracking(mem, grades)

    promotions = propose_promotions(grades, mem, min_models_broken=min_models_broken)
    retirements = propose_retirements(mem, max_consecutive_passes=max_consecutive_passes)

    click.echo(f"Grades loaded: {len(grades)}")
    click.echo(f"Promotion proposals: {len(promotions)}")
    for tid in promotions:
        click.echo(f"  PROMOTE {tid} → regression")
    click.echo(f"Retirement proposals: {len(retirements)}")
    for tid in retirements:
        click.echo(f"  RETIRE {tid} → retired")

    if apply:
        for tid in promotions:
            apply_promotion(mem, tid)
        for tid in retirements:
            apply_retirement(mem, tid)
        save_suite_membership(mem, membership)
        click.echo(f"Applied changes to {membership}")
    else:
        save_suite_membership(mem, membership)
        click.echo("Tracking updated (dry-run, no promotions/retirements applied)")


# --- cross-repo ---


@main.command("cross-repo")
@click.option("--results", required=True, type=click.Path(exists=True), help="RadSlice results dir")
@click.option("--lostbench-results", type=click.Path(exists=True), help="LostBench results dir")
@click.option("--tasks-dir", default="configs/tasks", help="Tasks directory")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def cross_repo(results, lostbench_results, tasks_dir, fmt):
    """Correlate RadSlice findings with LostBench results."""
    from radslice.analysis.cross_repo import (
        correlate_findings,
        generate_cross_repo_report,
    )

    findings = correlate_findings(results, lostbench_results, tasks_dir)

    if fmt == "json":
        import dataclasses

        click.echo(
            json.dumps(
                [dataclasses.asdict(f) for f in findings],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(generate_cross_repo_report(findings))


# --- calibration ---


@main.command()
@click.option(
    "--results-dirs",
    required=True,
    multiple=True,
    type=click.Path(exists=True),
    help="Results directories to analyze",
)
@click.option(
    "--calibration-set",
    default="configs/calibration/calibration_set.yaml",
    help="Calibration set YAML",
)
@click.option(
    "--human-grades",
    default="configs/calibration/human_grades.jsonl",
    help="Human reference grades",
)
@click.option("--kappa-threshold", default=0.60, type=float, help="Min kappa threshold")
@click.option("--agreement-threshold", default=0.70, type=float, help="Min agreement threshold")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def calibration(
    results_dirs, calibration_set, human_grades, kappa_threshold, agreement_threshold, fmt
):
    """Check calibration drift across evaluation runs."""
    import yaml as _yaml

    from radslice.analysis.calibration_drift import (
        compare_to_human,
        compute_calibration_drift,
        format_drift_report,
    )

    # Load calibration set
    cal_path = Path(calibration_set)
    cal_ids = None
    if cal_path.exists():
        with open(cal_path) as f:
            cal_data = _yaml.safe_load(f) or {}
        cal_ids = set(cal_data.get("task_ids", []))

    # Aggregate grades from all result dirs
    all_grades = []
    for rdir in results_dirs:
        all_grades.extend(_load_grades(rdir))

    if not all_grades:
        click.echo("No grades found in results directories.", err=True)
        return

    report = compute_calibration_drift(
        all_grades,
        calibration_set_ids=cal_ids,
        kappa_threshold=kappa_threshold,
        agreement_threshold=agreement_threshold,
    )

    # Optional human comparison
    human_result = compare_to_human(human_grades, all_grades)
    if human_result:
        # Reconstruct report with human comparison
        from dataclasses import replace

        report = replace(report, human_comparison=human_result)

    if fmt == "json":
        import dataclasses

        click.echo(json.dumps(dataclasses.asdict(report), indent=2, default=str))
    else:
        click.echo(format_drift_report(report))


# --- helpers ---


def _load_grades(results_dir: str) -> list:
    """Load grades from a results directory."""
    grades_path = Path(results_dir) / "grades.jsonl"
    if not grades_path.exists():
        raise click.UsageError(f"No grades.jsonl in {results_dir}")

    grades = []
    with open(grades_path) as f:
        for line in f:
            if line.strip():
                grades.append(json.loads(line))
    return grades


def _build_providers(models: list[dict]) -> dict:
    """Build provider instances from model configs."""
    providers = {}
    provider_names = {m["provider"] for m in models}

    for name in provider_names:
        if name == "openai":
            from radslice.providers.openai import OpenAIProvider

            providers[name] = OpenAIProvider()
        elif name == "anthropic":
            from radslice.providers.anthropic import AnthropicProvider

            providers[name] = AnthropicProvider()
        elif name == "google":
            from radslice.providers.google import GoogleProvider

            providers[name] = GoogleProvider()
        else:
            raise click.UsageError(f"Unknown provider: {name}")

    return providers


def _get_judge_provider(judge_model: str, providers: dict):
    """Get or create a provider for the judge model (cross-vendor)."""
    # Cross-vendor: use OpenAI for judging Claude/Gemini, Anthropic for judging OpenAI
    if "gpt" in judge_model.lower():
        if "openai" in providers:
            return providers["openai"]
        from radslice.providers.openai import OpenAIProvider

        return OpenAIProvider()
    elif "opus" in judge_model.lower() or "sonnet" in judge_model.lower():
        if "anthropic" in providers:
            return providers["anthropic"]
        from radslice.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    elif "gemini" in judge_model.lower():
        if "google" in providers:
            return providers["google"]
        from radslice.providers.google import GoogleProvider

        return GoogleProvider()

    # Default: try OpenAI
    if "openai" in providers:
        return providers["openai"]
    from radslice.providers.openai import OpenAIProvider

    return OpenAIProvider()


if __name__ == "__main__":
    main()
