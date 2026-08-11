"""Measure first, cached, and point-change calls used by the Streamlit UI."""

from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.ui_runtime import (
    calculate_route_cached,
    calculate_shadows_cached,
    load_dataset_cached,
)


def measure(
    data_directory: Path,
    data_version: str,
    destination: tuple[float, float],
) -> dict[str, float]:
    departure = "2024-08-01T14:00:00+09:00"
    started = perf_counter()
    load_dataset_cached(str(data_directory), data_version)
    after_data = perf_counter()
    calculate_shadows_cached(str(data_directory), data_version, departure)
    after_shadows = perf_counter()
    route = calculate_route_cached(
        str(data_directory),
        data_version,
        departure,
        34.2325,
        135.1917,
        destination[0],
        destination[1],
        10.0,
    )
    finished = perf_counter()
    return {
        "total_seconds": finished - started,
        "dataset_call_seconds": after_data - started,
        "shadow_call_seconds": after_shadows - after_data,
        "route_call_seconds": finished - after_shadows,
        "route_distance_m": route.result.distance_m,
        "shade_ratio_pct": route.result.shade_ratio_pct,
    }


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data" / "prepared" / "wakayama-station",
    )
    args = parser.parse_args()
    data_directory = args.data_dir.resolve()
    data_version = str((data_directory / "manifest.json").stat().st_mtime_ns)
    results = {
        "first": measure(data_directory, data_version, (34.2241, 135.1906)),
        "cached": measure(data_directory, data_version, (34.2241, 135.1906)),
        "point_changed": measure(data_directory, data_version, (34.2250, 135.1910)),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
