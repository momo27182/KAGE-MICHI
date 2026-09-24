from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.building_comparison import (
    BuildingComparisonConfig,
    compare_prepared_buildings,
    write_comparison_report,
)
from kage_michi.models import GeoPoint


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare prepared OSM and PLATEAU buildings offline")
    parser.add_argument("--osm", type=Path, default=ROOT / "data/prepared/wakayama-station")
    parser.add_argument("--plateau", type=Path, default=ROOT / "data/prepared/plateau/wakayama-station")
    parser.add_argument("--departure", default="2026-08-11T14:00:00+09:00")
    parser.add_argument("--radius-m", type=int, default=1700)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark-results/plateau-osm-comparison.json")
    args = parser.parse_args()
    config = BuildingComparisonConfig(GeoPoint(34.2325, 135.1917), args.radius_m, datetime.fromisoformat(args.departure))
    report = compare_prepared_buildings(args.osm, args.plateau, config)
    write_comparison_report(report, args.output)
    print(f"report: {args.output}")
    print(f"osm_buildings: {report['buildings']['osm']['count']}")
    print(f"plateau_buildings: {report['buildings']['plateau']['count']}")
    print(f"footprint_iou: {report['footprints']['intersection_over_union']}")
    print(f"shadow_iou: {report['shadows']['intersection_over_union']}")
    print(f"total_seconds: {report['performance_seconds']['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
