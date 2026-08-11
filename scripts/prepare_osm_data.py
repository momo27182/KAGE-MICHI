from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.osm_prepared import (
    OsmPreparationConfig,
    load_prepared_dataset,
    prepare_osm_dataset,
)
from kage_michi.models import GeoPoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download OSM once and save projected KAGE-MICHI artifacts"
    )
    parser.add_argument("--latitude", type=float, default=34.2325)
    parser.add_argument("--longitude", type=float, default=135.1917)
    parser.add_argument("--radius-m", type=int, default=1_700)
    parser.add_argument("--crs", default="EPSG:6676")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "prepared" / "wakayama-station")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "osmnx-cache")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = OsmPreparationConfig(
        center=GeoPoint(args.latitude, args.longitude),
        radius_m=args.radius_m,
        projected_crs=args.crs,
    )
    started = perf_counter()
    destination = prepare_osm_dataset(
        config,
        args.output,
        cache_dir=args.cache_dir,
        overwrite=args.overwrite,
    )
    preparation_seconds = perf_counter() - started

    started = perf_counter()
    dataset = load_prepared_dataset(destination)
    load_seconds = perf_counter() - started
    payload = dataset.payload
    print(f"prepared: {destination}")
    print(f"preparation_seconds: {preparation_seconds:.6f}")
    print(f"offline_load_seconds: {load_seconds:.6f}")
    print(f"road_nodes: {payload.graph.number_of_nodes()}")
    print(f"road_edges: {payload.graph.number_of_edges()}")
    print(f"buildings: {len(payload.buildings)}")
    print(f"spots: {len(payload.spots)}")
    print(f"source: {dataset.source}")
    print(f"acquired_at: {dataset.acquired_at}")
    print(f"scope: {dataset.scope}")
    print(f"crs: {dataset.crs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
