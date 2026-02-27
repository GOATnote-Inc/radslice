"""Markdown/JSON/CSV report generation from analysis results."""

from __future__ import annotations

import csv
import io
import json


def format_report(data: dict, fmt: str = "markdown") -> str:
    """Format analysis data as markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(data, indent=2, default=str)
    elif fmt == "csv":
        return _to_csv(data)
    else:
        return _to_markdown(data)


def _to_markdown(data: dict) -> str:
    """Generate markdown report."""
    lines = ["# RadSlice Evaluation Report", ""]

    if "total_grades" in data:
        lines.append(f"**Total grades:** {data['total_grades']}")
        lines.append("")

    # Per-modality breakdown
    if "by_modality" in data:
        lines.append("## Per-Modality Results")
        lines.append("")
        lines.append("| Modality | Tasks | Passed | Rate | pass@k | pass^k | Wilson CI |")
        lines.append("|----------|-------|--------|------|--------|--------|-----------|")
        for mod, info in sorted(data["by_modality"].items()):
            wci = info.get("wilson_ci", (0, 1))
            lines.append(
                f"| {mod} | {info['total_grades']} | {info['passed']} "
                f"| {info['pass_rate']:.1%} | {info.get('pass_at_k', 0):.3f} "
                f"| {info.get('pass_pow_k', 0):.3f} | [{wci[0]:.3f}, {wci[1]:.3f}] |"
            )
        lines.append("")

        # Failure classes
        lines.append("### Failure Classes")
        lines.append("")
        lines.append("| Modality | Class A | Class B | Class C | Class D | Class E |")
        lines.append("|----------|---------|---------|---------|---------|---------|")
        for mod, info in sorted(data["by_modality"].items()):
            fc = info.get("failure_classes", {})
            lines.append(
                f"| {mod} | {fc.get('A', 0)} | {fc.get('B', 0)} | {fc.get('C', 0)} "
                f"| {fc.get('D', 0)} | {fc.get('E', 0)} |"
            )
        lines.append("")

    # Per-anatomy breakdown
    if "by_anatomy" in data:
        lines.append("## Per-Anatomy Results")
        lines.append("")
        lines.append("| Anatomy | Tasks | Passed | Rate | Wilson CI |")
        lines.append("|---------|-------|--------|------|-----------|")
        for anat, info in sorted(data["by_anatomy"].items()):
            wci = info.get("wilson_ci", (0, 1))
            lines.append(
                f"| {anat} | {info['total_grades']} | {info['passed']} "
                f"| {info['pass_rate']:.1%} | [{wci[0]:.3f}, {wci[1]:.3f}] |"
            )
        lines.append("")

    # Comparison / regression
    if "comparison" in data:
        comp = data["comparison"]
        lines.append("## Regression Analysis")
        lines.append("")
        lines.append(f"**Run A:** {data.get('run_a', 'current')}")
        lines.append(f"**Run B:** {comp.get('run_b', 'prior')}")
        lines.append("")
        reg = comp.get("regression", {})
        if reg.get("overall_regression"):
            lines.append(
                f"**REGRESSION DETECTED** in: {', '.join(reg.get('regressed_modalities', []))}"
            )
        else:
            lines.append("**No regression detected.**")
        lines.append("")

        if "details" in reg:
            lines.append("| Modality | Current | Prior | z-score | Regression |")
            lines.append("|----------|---------|-------|---------|------------|")
            for mod, detail in sorted(reg["details"].items()):
                cr = detail["current"]
                pr = detail["prior"]
                flag = "YES" if detail["regression"] else ""
                lines.append(
                    f"| {mod} | {cr['passed']}/{cr['total']} "
                    f"| {pr['passed']}/{pr['total']} "
                    f"| {detail['z_score']:.3f} | {flag} |"
                )
            lines.append("")

    return "\n".join(lines)


def _to_csv(data: dict) -> str:
    """Generate CSV report from modality breakdown."""
    output = io.StringIO()
    writer = csv.writer(output)

    if "by_modality" in data:
        writer.writerow(
            [
                "modality",
                "total",
                "passed",
                "pass_rate",
                "pass_at_k",
                "pass_pow_k",
                "wilson_ci_lo",
                "wilson_ci_hi",
                "mean_score",
            ]
        )
        for mod, info in sorted(data["by_modality"].items()):
            wci = info.get("wilson_ci", (0, 1))
            writer.writerow(
                [
                    mod,
                    info["total_grades"],
                    info["passed"],
                    f"{info['pass_rate']:.4f}",
                    f"{info.get('pass_at_k', 0):.4f}",
                    f"{info.get('pass_pow_k', 0):.4f}",
                    f"{wci[0]:.4f}",
                    f"{wci[1]:.4f}",
                    f"{info.get('mean_score', 0):.4f}",
                ]
            )

    return output.getvalue()
