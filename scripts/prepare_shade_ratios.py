from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.precomputed_shade import (
    ShadeTimeRange,
    generate_prepared_shade_artifact,
    load_shade_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precompute five-minute road shade ratios offline"
    )
    parser.add_argument("--osm", type=Path, default=ROOT / "data/prepared/wakayama-station")
    parser.add_argument(
        "--plateau",
        type=Path,
        default=ROOT / "data/prepared/plateau/wakayama-station",
    )
    parser.add_argument("--date", type=date.fromisoformat, default=date(2026, 8, 11))
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--start-time", type=time.fromisoformat, default=time.min)
    parser.add_argument("--end-time", type=time.fromisoformat)
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--spacing-m", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    zone = ZoneInfo(args.timezone)
    start = datetime.combine(args.date, args.start_time, zone)
    end = (
        datetime.combine(args.date, args.end_time, zone)
        if args.end_time is not None
        else datetime.combine(args.date + timedelta(days=1), time.min, zone)
        - timedelta(minutes=args.interval_minutes)
    )
    destination = args.output or (
        ROOT / "data/prepared/shade/wakayama-station" / args.date.isoformat()
    )
    time_range = ShadeTimeRange(
        start,
        end,
        interval_minutes=args.interval_minutes,
        sample_spacing_m=args.spacing_m,
    )
    generate_prepared_shade_artifact(
        args.osm, args.plateau, destination, time_range
    )
    loaded = load_shade_artifact(destination)
    print(f"artifact: {destination}")
    print(f"timestamps: {loaded.manifest.counts['timestamps']}")
    print(f"daylight_timestamps: {loaded.manifest.counts['daylight_timestamps']}")
    print(f"edges: {loaded.manifest.counts['edges']}")
    print(f"generation_seconds: {loaded.manifest.metrics['generation_seconds']}")
    print(f"output_bytes: {loaded.manifest.metrics['output_bytes']}")
    print(
        "validation_load_seconds: "
        f"{loaded.manifest.metrics['validation_load_seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
