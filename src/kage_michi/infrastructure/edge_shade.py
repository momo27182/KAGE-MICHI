"""Pure helpers for measuring partial shade along projected road edges."""

from __future__ import annotations

from math import ceil

from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge
from shapely.prepared import prep


def normalize_edge_geometry(geometry: BaseGeometry) -> LineString:
    """Return a non-empty line suitable for interpolation and length measures."""
    if isinstance(geometry, LineString) and not geometry.is_empty and geometry.length > 0:
        return geometry
    if isinstance(geometry, MultiLineString) and not geometry.is_empty:
        merged = linemerge(geometry)
        if isinstance(merged, LineString) and merged.length > 0:
            return merged
    raise ValueError("edge geometry must be a non-empty continuous line")


def sampled_shade_ratio(
    line: BaseGeometry,
    shadows: BaseGeometry | None,
    spacing_m: float,
) -> tuple[float, int]:
    """Estimate shaded length using centres of equal-length sampling bins."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    normalized = normalize_edge_geometry(line)
    sample_count = max(1, ceil(normalized.length / spacing_m))
    if shadows is None or shadows.is_empty:
        return 0.0, sample_count

    prepared = prep(shadows)
    shaded = sum(
        prepared.covers(
            normalized.interpolate((index + 0.5) / sample_count, normalized=True)
        )
        for index in range(sample_count)
    )
    return shaded / sample_count, sample_count


def intersection_shade_ratio(
    line: BaseGeometry,
    shadows: BaseGeometry | None,
) -> float:
    """Calculate the exact shaded share of a line for comparison purposes."""
    normalized = normalize_edge_geometry(line)
    if shadows is None or shadows.is_empty:
        return 0.0
    return min(1.0, max(0.0, normalized.intersection(shadows).length / normalized.length))
