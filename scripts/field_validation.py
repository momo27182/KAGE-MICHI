from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.field_validation import (
    read_observations,
    summarize_observations,
    write_observation_template,
    write_validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or summarize field shadow validation records")
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser("template", help="write a CSV observation template")
    template.add_argument("output", type=Path)
    summarize = subparsers.add_parser("summarize", help="validate a CSV and write its JSON summary")
    summarize.add_argument("input", type=Path)
    summarize.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "template":
        result = write_observation_template(args.output)
        print(f"template: {result}")
        return 0

    observations = read_observations(args.input)
    report = summarize_observations(observations)
    result = write_validation_report(report, args.output)
    print(f"report: {result}")
    print(f"observations: {report['observation_count']}")
    print(f"mean_absolute_error_percentage_points: {report['mean_absolute_error_percentage_points']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
