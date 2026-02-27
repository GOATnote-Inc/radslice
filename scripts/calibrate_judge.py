"""Run human calibration analysis: compare judge grades to human grades."""

from __future__ import annotations

import argparse
import json

from radslice.grading.calibration import compute_calibration, load_calibration


def main():
    parser = argparse.ArgumentParser(description="Run judge calibration analysis")
    parser.add_argument("--human", required=True, help="Human calibration JSONL")
    parser.add_argument("--judge", required=True, help="Judge grades JSONL")
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    human_entries = load_calibration(args.human)
    judge_entries = load_calibration(args.judge)

    print(f"Human entries: {len(human_entries)}")
    print(f"Judge entries: {len(judge_entries)}")

    result = compute_calibration(human_entries, judge_entries)

    print(f"\n--- Calibration Results ---")
    print(f"Tasks compared: {result.n_tasks}")
    print(f"Cohen's kappa: {result.cohens_kappa:.3f}")
    print(f"Percent agreement: {result.percent_agreement:.1%}")
    print(f"\nPer-dimension correlation:")
    for dim, corr in sorted(result.per_dimension_correlation.items()):
        print(f"  {dim}: {corr:.3f}")

    if result.cohens_kappa >= 0.6:
        print("\n✓ Kappa >= 0.60: moderate-to-substantial agreement")
    else:
        print("\n✗ Kappa < 0.60: insufficient agreement — review judge prompt")

    if args.output:
        output = {
            "cohens_kappa": result.cohens_kappa,
            "percent_agreement": result.percent_agreement,
            "per_dimension_correlation": result.per_dimension_correlation,
            "n_tasks": result.n_tasks,
            "confusion_matrix": result.confusion_matrix,
        }
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
