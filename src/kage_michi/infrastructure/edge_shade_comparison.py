"""Offline comparison of edge shade-ratio methods on prepared data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from statistics import fmean
from time import perf_counter

import networkx as nx
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from ..data import SpatialDataset
from ..models import GeoPoint
from .edge_shade import intersection_shade_ratio, normalize_edge_geometry, sampled_shade_ratio
from .osm_prepared import load_prepared_dataset
from .plateau_prepared import load_prepared_plateau_buildings
from .shadow_calculator import BuildingShadowCalculator


COMPARISON_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EdgeShadeComparisonConfig:
    center: GeoPoint = GeoPoint(34.2325, 135.1917)
    departure: datetime | None = None
    sample_spacings_m: tuple[float, ...] = (5.0, 10.0)

    def __post_init__(self) -> None:
        if self.departure is None or self.departure.utcoffset() is None:
            raise ValueError("departure must include timezone information")
        if not self.sample_spacings_m or any(value <= 0 for value in self.sample_spacings_m):
            raise ValueError("sample spacings must be positive")


def compare_edge_shade_methods(
    graph: nx.MultiDiGraph,
    shadows: BaseGeometry | None,
    spacings_m: tuple[float, ...] = (5.0, 10.0),
) -> dict[str, object]:
    """Compare midpoint and sampled estimates against intersection length."""
    lines = [_edge_line(graph, u, v, edge) for u, v, _, edge in graph.edges(keys=True, data=True)]

    exact_started = perf_counter()
    exact = [intersection_shade_ratio(line, shadows) for line in lines]
    exact_seconds = perf_counter() - exact_started

    midpoint_started = perf_counter()
    prepared = prep(shadows) if shadows is not None and not shadows.is_empty else None
    midpoint = [
        float(prepared.covers(line.interpolate(0.5, normalized=True))) if prepared else 0.0
        for line in lines
    ]
    midpoint_seconds = perf_counter() - midpoint_started

    methods: dict[str, object] = {
        "midpoint": _method_metrics(midpoint, exact, midpoint_seconds, len(lines)),
        "intersection_length": {
            **_method_metrics(exact, exact, exact_seconds, len(lines)),
            "reference": True,
        },
    }
    for spacing in spacings_m:
        started = perf_counter()
        sample_counts = []
        values = []
        for line in lines:
            ratio, count = sampled_shade_ratio(line, shadows, spacing)
            values.append(ratio)
            sample_counts.append(count)
        seconds = perf_counter() - started
        methods[f"sample_{_format_spacing(spacing)}m"] = {
            **_method_metrics(values, exact, seconds, len(lines)),
            "sample_count": sum(sample_counts),
            "mean_samples_per_edge": round(fmean(sample_counts), 3) if sample_counts else 0.0,
        }

    float32_bytes = len(lines) * 4
    return {
        "edge_count": len(lines),
        "methods": methods,
        "storage_estimate": {
            "float32_bytes_per_time_slice": float32_bytes,
            "float32_mib_per_time_slice": round(float32_bytes / 1024**2, 6),
            "float32_mib_for_24h_at_5min": round(float32_bytes * 288 / 1024**2, 3),
            "note": "raw edge ratios only; file/container indexes and metadata are excluded",
        },
    }


def compare_prepared_edge_shade(
    osm_directory: str | Path,
    plateau_directory: str | Path,
    config: EdgeShadeComparisonConfig,
) -> dict[str, object]:
    """Build one PLATEAU shadow and compare road evaluation methods offline."""
    started = perf_counter()
    osm = load_prepared_dataset(osm_directory)
    plateau = load_prepared_plateau_buildings(plateau_directory)
    buildings = plateau.buildings[["height_m", "geometry"]].rename(
        columns={"height_m": "height"}
    )
    buildings = buildings.explode(index_parts=False, ignore_index=True)
    buildings = buildings[buildings.geometry.geom_type == "Polygon"].reset_index(drop=True)
    payload = type(
        "EdgeShadePayload",
        (),
        {"buildings": buildings, "manifest": plateau.manifest},
    )()
    shadow_dataset = SpatialDataset(
        payload, "PLATEAU LOD1", "fixed", osm.scope, str(buildings.crs)
    )
    shadow_started = perf_counter()
    shadow = BuildingShadowCalculator(center=config.center).calculate(
        shadow_dataset, config.departure
    )
    shadow_seconds = perf_counter() - shadow_started
    comparison = compare_edge_shade_methods(
        osm.payload.graph, shadow.geometry, config.sample_spacings_m
    )
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "config": {
            "center": asdict(config.center),
            "departure": config.departure.isoformat(),
            "projected_crs": str(buildings.crs),
            "sample_spacings_m": list(config.sample_spacings_m),
        },
        "sources": {
            "roads": "prepared OpenStreetMap walking graph",
            "shadows": "prepared PLATEAU LOD1 buildings and current convex-hull shadow model",
        },
        "shadow_generation_seconds": round(shadow_seconds, 6),
        **comparison,
        "total_seconds": round(perf_counter() - started, 6),
        "limitations": [
            "Intersection length is a geometric reference for this shadow model, not ground truth.",
            "Storage estimates exclude file format overhead and compression.",
            "Only one fixed date and time is compared in this task.",
        ],
    }


def write_edge_shade_report(report: dict[str, object], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _edge_line(graph: nx.MultiDiGraph, u: int, v: int, edge: dict[str, object]) -> LineString:
    geometry = edge.get("geometry")
    if geometry is None:
        geometry = LineString(
            [
                (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
                (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
            ]
        )
    return normalize_edge_geometry(geometry)


def _method_metrics(
    values: list[float], exact: list[float], seconds: float, edge_count: int
) -> dict[str, object]:
    errors = [abs(value - reference) for value, reference in zip(values, exact)]
    partial = sum(0.0 < value < 1.0 for value in values)
    return {
        "seconds": round(seconds, 6),
        "microseconds_per_edge": round(seconds * 1_000_000 / edge_count, 3) if edge_count else 0.0,
        "mean_absolute_error": round(fmean(errors), 6) if errors else 0.0,
        "maximum_absolute_error": round(max(errors), 6) if errors else 0.0,
        "partial_shade_edge_count": partial,
        "mean_shade_ratio": round(fmean(values), 6) if values else 0.0,
    }


def _format_spacing(value: float) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric).replace(".", "_")
