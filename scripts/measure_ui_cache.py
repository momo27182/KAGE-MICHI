"""Measure precomputed-shade route calls used by the Streamlit UI."""

from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.ui_runtime import (
    calculate_route_comparison_cached,
    load_dataset_cached,
    load_precomputed_shade_cached,
)


def measure(
    data_directory: Path,
    shade_directory: Path,
    data_version: str,
    shade_version: str,
    departure: str,
    destination: tuple[float, float],
) -> dict[str, float | str]:
    started = perf_counter()
    route = calculate_route_comparison_cached(
        str(data_directory),
        data_version,
        str(shade_directory),
        shade_version,
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
        "route_call_seconds": route.elapsed_seconds,
        "shade_load_seconds": route.shade_load_seconds,
        "resolved_shade_time": route.shade_time.resolved.isoformat(),
        "route_distance_m": route.result.shade_optimized.distance_m,
        "shade_ratio_pct": route.result.shade_optimized.shade_ratio_pct,
    }


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data" / "prepared" / "wakayama-station",
    )
    parser.add_argument(
        "--shade-dir",
        type=Path,
        default=ROOT / "data" / "prepared" / "shade" / "wakayama-station" / "2026-08-11",
    )
    args = parser.parse_args()
    data_directory = args.data_dir.resolve()
    shade_directory = args.shade_dir.resolve()
    data_version = str((data_directory / "manifest.json").stat().st_mtime_ns)
    shade_version = str((shade_directory / "manifest.json").stat().st_mtime_ns)
    load_dataset_cached.clear()
    load_precomputed_shade_cached.clear()
    calculate_route_comparison_cached.clear()
    results = {
        "first": measure(
            data_directory, shade_directory, data_version, shade_version,
            "2026-08-11T14:04:00+09:00", (34.2241, 135.1906),
        ),
        "cached": measure(
            data_directory, shade_directory, data_version, shade_version,
            "2026-08-11T14:04:00+09:00", (34.2241, 135.1906),
        ),
        "time_changed": measure(
            data_directory, shade_directory, data_version, shade_version,
            "2026-08-11T14:09:00+09:00", (34.2241, 135.1906),
        ),
        "point_changed": measure(
            data_directory, shade_directory, data_version, shade_version,
            "2026-08-11T14:09:00+09:00", (34.2250, 135.1910),
        ),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
