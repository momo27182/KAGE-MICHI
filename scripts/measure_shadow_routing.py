"""Measure shadow calculation and route search independently on prepared data."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.osm_prepared import PreparedOsmDataSource
from kage_michi.infrastructure.shade_route_planner import MidpointShadeRoutePlanner
from kage_michi.infrastructure.shadow_calculator import BuildingShadowCalculator
from kage_michi.models import GeoPoint


DEFAULT_CASE = "wakayama_station_to_tanakaguchi_summer_afternoon"


def load_case(case_id: str) -> dict:
    document = json.loads((ROOT / "benchmarks" / "cases.json").read_text(encoding="utf-8"))
    for case in document["cases"]:
        if case["id"] == case_id:
            return case
    raise ValueError(f"unknown benchmark case: {case_id}")


def point(raw: dict) -> GeoPoint:
    return GeoPoint(latitude=raw["latitude"], longitude=raw["longitude"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", default=DEFAULT_CASE)
    parser.add_argument(
        "--data-dir", type=Path, default=ROOT / "data" / "prepared" / "wakayama-station"
    )
    args = parser.parse_args()

    case = load_case(args.case_id)
    start = point(case["start"])
    destination = point(case["destination"])
    departure = datetime.fromisoformat(case["departure_jst"])
    dataset = PreparedOsmDataSource(args.data_dir).load(start, destination)

    shadow_calculator = BuildingShadowCalculator(center=start)
    started = perf_counter()
    shadows = shadow_calculator.calculate(dataset, departure)
    shadow_seconds = perf_counter() - started

    route_planner = MidpointShadeRoutePlanner(sun_penalty=case["sun_penalty"])
    started = perf_counter()
    route = route_planner.find_route(dataset, start, destination, shadows)
    route_seconds = perf_counter() - started

    print(
        json.dumps(
            {
                "case_id": case["id"],
                "shadow_calculation_seconds": round(shadow_seconds, 6),
                "route_search_seconds": round(route_seconds, 6),
                "building_count": shadows.building_count,
                "shadow_polygon_count": shadows.shadow_polygon_count,
                "solar_altitude_deg": round(shadows.solar_altitude_deg, 3),
                "route_node_count": len(route.node_ids),
                "route_distance_m": round(route.distance_m, 3),
                "sunny_distance_m": round(route.sunny_distance_m, 3),
                "shade_ratio_pct": round(route.shade_ratio_pct, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
