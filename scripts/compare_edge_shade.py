from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.edge_shade_comparison import (
    EdgeShadeComparisonConfig,
    compare_prepared_edge_shade,
    write_edge_shade_report,
)
from kage_michi.models import GeoPoint


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare road shade-ratio methods offline")
    parser.add_argument("--osm", type=Path, default=ROOT / "data/prepared/wakayama-station")
    parser.add_argument("--plateau", type=Path, default=ROOT / "data/prepared/plateau/wakayama-station")
    parser.add_argument("--departure", default="2026-08-11T14:00:00+09:00")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark-results/edge-shade-comparison.json")
    args = parser.parse_args()
    config = EdgeShadeComparisonConfig(
        center=GeoPoint(34.2325, 135.1917),
        departure=datetime.fromisoformat(args.departure),
    )
    report = compare_prepared_edge_shade(args.osm, args.plateau, config)
    write_edge_shade_report(report, args.output)
    print(f"report: {args.output}")
    print(f"edge_count: {report['edge_count']}")
    for name, metrics in report["methods"].items():
        print(f"{name}: {metrics}")
    print(f"total_seconds: {report['total_seconds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
