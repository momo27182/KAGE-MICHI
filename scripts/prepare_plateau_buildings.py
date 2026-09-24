from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.plateau_prepared import (
    PlateauPreparationConfig,
    load_prepared_plateau_buildings,
    mesh_codes_for_radius,
    prepare_plateau_buildings,
)
from kage_michi.models import GeoPoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare local PLATEAU CityGML buildings for KAGE-MICHI"
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Downloaded CityGML ZIP or directory containing udx/bldg/*.gml",
    )
    parser.add_argument("--latitude", type=float, default=34.2325)
    parser.add_argument("--longitude", type=float, default=135.1917)
    parser.add_argument("--radius-m", type=int, default=1_700)
    parser.add_argument("--crs", default="EPSG:6676")
    parser.add_argument("--source-url")
    parser.add_argument("--source-etag")
    parser.add_argument("--source-acquired-at-utc")
    parser.add_argument(
        "--mesh",
        action="append",
        default=[],
        help="Third-level mesh code; repeat for multiple meshes",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "prepared" / "plateau" / "wakayama-station",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    center = GeoPoint(args.latitude, args.longitude)
    meshes = tuple(args.mesh) or mesh_codes_for_radius(center, args.radius_m)
    config = PlateauPreparationConfig(
        center=center,
        radius_m=args.radius_m,
        projected_crs=args.crs,
        mesh_codes=meshes,
        **({"source_url": args.source_url} if args.source_url else {}),
        source_etag=args.source_etag,
        source_acquired_at_utc=args.source_acquired_at_utc,
    )
    destination = prepare_plateau_buildings(
        args.source, args.output, config, overwrite=args.overwrite
    )
    prepared = load_prepared_plateau_buildings(destination)
    manifest = prepared.manifest
    print(f"prepared: {destination}")
    print(f"mesh_codes: {','.join(manifest.selected_mesh_codes)}")
    print(f"buildings: {manifest.counts['buildings']}")
    print(f"missing_height: {manifest.counts['missing_height']}")
    print(f"lod2_buildings: {manifest.counts['lod2_buildings']}")
    print(f"preparation_seconds: {manifest.metrics['preparation_seconds']}")
    print(f"peak_memory_bytes: {manifest.metrics['peak_memory_bytes']}")
    print(f"output_bytes: {manifest.metrics['output_bytes']}")
    print(f"crs: {manifest.projected_crs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
