"""Tests for cli.py — Click CLI commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from radslice.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCLIVersion:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCLIHelp:
    def test_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "RadSlice" in result.output

    def test_run_help(self, runner):
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--matrix" in result.output
        assert "--n-trials" in result.output

    def test_grade_help(self, runner):
        result = runner.invoke(main, ["grade", "--help"])
        assert result.exit_code == 0
        assert "--results" in result.output

    def test_analyze_help(self, runner):
        result = runner.invoke(main, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--per-modality" in result.output

    def test_report_help(self, runner):
        result = runner.invoke(main, ["report", "--help"])
        assert result.exit_code == 0
        assert "--compare" in result.output

    def test_corpus_help(self, runner):
        result = runner.invoke(main, ["corpus", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "download" in result.output


class TestCorpusValidate:
    def test_validate_valid_tasks(self, runner, sample_tasks_dir):
        result = runner.invoke(main, ["corpus", "validate", "--tasks-dir", str(sample_tasks_dir)])
        assert result.exit_code == 0
        assert "Valid: 5" in result.output

    def test_validate_missing_dir(self, runner, tmp_path):
        result = runner.invoke(main, ["corpus", "validate", "--tasks-dir", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_validate_empty_dir(self, runner, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = runner.invoke(main, ["corpus", "validate", "--tasks-dir", str(empty)])
        assert result.exit_code == 0
        assert "Valid: 0" in result.output


class TestAnalyze:
    def test_analyze_per_modality(self, runner, tmp_path, sample_grades):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        grades_file = results_dir / "grades.jsonl"
        with open(grades_file, "w") as f:
            for g in sample_grades:
                f.write(json.dumps(g) + "\n")

        result = runner.invoke(main, ["analyze", "--results", str(results_dir), "--per-modality"])
        assert result.exit_code == 0
        assert "Per-Modality" in result.output

    def test_analyze_json_format(self, runner, tmp_path, sample_grades):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        with open(results_dir / "grades.jsonl", "w") as f:
            for g in sample_grades:
                f.write(json.dumps(g) + "\n")

        result = runner.invoke(main, ["analyze", "--results", str(results_dir), "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_grades" in parsed

    def test_analyze_csv_format(self, runner, tmp_path, sample_grades):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        with open(results_dir / "grades.jsonl", "w") as f:
            for g in sample_grades:
                f.write(json.dumps(g) + "\n")

        result = runner.invoke(
            main, ["analyze", "--results", str(results_dir), "--per-modality", "--format", "csv"]
        )
        assert result.exit_code == 0
        assert "modality" in result.output

    def test_analyze_missing_results(self, runner, tmp_path):
        result = runner.invoke(main, ["analyze", "--results", str(tmp_path / "nope")])
        assert result.exit_code != 0


class TestReport:
    def test_basic_report(self, runner, tmp_path, sample_grades):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        with open(results_dir / "grades.jsonl", "w") as f:
            for g in sample_grades:
                f.write(json.dumps(g) + "\n")

        result = runner.invoke(main, ["report", "--results", str(results_dir)])
        assert result.exit_code == 0

    def test_compare_report(self, runner, tmp_path, sample_grades):
        for name in ["run_a", "run_b"]:
            d = tmp_path / name
            d.mkdir()
            with open(d / "grades.jsonl", "w") as f:
                for g in sample_grades:
                    f.write(json.dumps(g) + "\n")

        result = runner.invoke(
            main,
            [
                "report",
                "--results",
                str(tmp_path / "run_a"),
                "--compare",
                str(tmp_path / "run_b"),
            ],
        )
        assert result.exit_code == 0


class TestRunCommand:
    def test_run_requires_args(self, runner):
        result = runner.invoke(main, ["run"])
        assert result.exit_code != 0
