from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.benchmark_cases import load_benchmark_cases
from kage_michi.legacy_benchmark import (
    case_is_in_scope,
    configure_osmnx_cache,
    create_shadow_polygon,
    load_legacy_data,
    render_route_map,
    solve_route,
)
from kage_michi.performance import PerformanceRecorder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure the legacy KAGE-MICHI pipeline")
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "benchmarks" / "cases.json"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "benchmark-results"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "data" / "osmnx-cache"
    )
    parser.add_argument(
        "--run-label",
        choices=("cold", "warm", "manual"),
        default="manual",
        help="Label used to keep cold and warm results separate",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = {case.case_id: case for case in load_benchmark_cases(args.cases)}
    if args.case_id not in cases:
        print(f"unknown case id: {args.case_id}", file=sys.stderr)
        return 2

    case = cases[args.case_id]
    recorder = PerformanceRecorder(
        run_id=case.case_id,
        metadata={
            "case_id": case.case_id,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cache_dir": str(args.cache_dir),
            "run_label": args.run_label,
        },
    )
    configure_osmnx_cache(args.cache_dir)

    if not case_is_in_scope(case):
        result = {"status": "out_of_scope"}
    elif case.start == case.destination:
        result = {"status": "no_route"}
    else:
        with recorder.measure("data_pipeline_total"):
            bundle = load_legacy_data(recorder)
        with recorder.measure("shadow_pipeline_total"):
            shadows = create_shadow_polygon(
                bundle.projected_buildings, case, recorder
            )
        with recorder.measure("routing_pipeline_total"):
            route_outcome = solve_route(bundle, case, shadows, recorder)
        if route_outcome is None:
            result = {"status": "no_route"}
        else:
            route_metrics, route = route_outcome
            with recorder.measure("presentation_pipeline_total"):
                render_route_map(bundle, case, shadows, route, recorder)
            result = {"status": "route", **route_metrics}

    recorder.metadata["result"] = result
    recorder.metadata["expected_status"] = case.expected_status
    recorder.metadata["expectation_met"] = result["status"] == case.expected_status
    output = recorder.write_json(
        args.output_dir / f"{case.case_id}__{args.run_label}.json"
    )
    print(json.dumps(recorder.as_dict(), ensure_ascii=False, indent=2))
    print(f"wrote: {output}")
    return 0 if recorder.metadata["expectation_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
