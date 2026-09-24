"""Reproducible offline comparison of prepared OSM and PLATEAU buildings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union

from ..data import SpatialDataset
from ..models import GeoPoint
from .osm_prepared import load_prepared_buildings
from .plateau_prepared import load_prepared_plateau_buildings
from .shadow_calculator import BuildingShadowCalculator


COMPARISON_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BuildingComparisonConfig:
    center: GeoPoint = GeoPoint(34.2325, 135.1917)
    radius_m: int = 1_700
    departure: datetime | None = None

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.departure is None or self.departure.utcoffset() is None:
            raise ValueError("departure must include timezone information")


def compare_prepared_buildings(
    osm_directory: str | Path,
    plateau_directory: str | Path,
    config: BuildingComparisonConfig,
) -> dict[str, object]:
    """Compare verified local artifacts without external communication."""
    started = perf_counter()
    osm, osm_manifest = load_prepared_buildings(osm_directory)
    plateau_prepared = load_prepared_plateau_buildings(plateau_directory)
    plateau = plateau_prepared.buildings
    if str(osm.crs) != str(plateau.crs):
        raise ValueError("OSM and PLATEAU CRS must match")

    crs = str(osm.crs)
    center = gpd.GeoSeries(
        [Point(config.center.longitude, config.center.latitude)], crs="EPSG:4326"
    ).to_crs(crs).iloc[0]
    scope = center.buffer(config.radius_m)
    osm = _clip_buildings(osm, scope)
    plateau = _clip_buildings(plateau, scope)

    geometry_started = perf_counter()
    osm_union = unary_union(list(osm.geometry))
    plateau_union = unary_union(list(plateau.geometry))
    shared_area = osm_union.intersection(plateau_union).area
    combined_area = osm_union.union(plateau_union).area
    geometry_seconds = perf_counter() - geometry_started

    osm_heights = pd.to_numeric(osm.get("height"), errors="coerce")
    plateau_heights = pd.to_numeric(plateau.get("height_m"), errors="coerce")
    shadow_started = perf_counter()
    osm_shadow = _calculate_shadow(osm, "height", osm_manifest, config)
    osm_shadow_seconds = perf_counter() - shadow_started
    shadow_started = perf_counter()
    plateau_shadow = _calculate_shadow(
        plateau, "height_m", plateau_prepared.manifest, config
    )
    plateau_shadow_seconds = perf_counter() - shadow_started
    osm_shadow_geometry = osm_shadow.geometry
    plateau_shadow_geometry = plateau_shadow.geometry
    shared_shadow_area = (
        osm_shadow_geometry.intersection(plateau_shadow_geometry).area
        if osm_shadow_geometry is not None and plateau_shadow_geometry is not None
        else 0.0
    )
    shadow_union_area = (
        osm_shadow_geometry.union(plateau_shadow_geometry).area
        if osm_shadow_geometry is not None and plateau_shadow_geometry is not None
        else 0.0
    )

    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "config": {
            "center": asdict(config.center),
            "radius_m": config.radius_m,
            "departure": config.departure.isoformat(),
            "projected_crs": crs,
        },
        "sources": {
            "osm": {
                "acquired_at_utc": osm_manifest.acquired_at_utc,
                "buildings_sha256": osm_manifest.sha256["buildings"],
                "height_provenance": "missing values replaced during OSM preparation",
                "default_height_m": osm_manifest.default_building_height_m,
            },
            "plateau": {
                "acquired_at_utc": plateau_prepared.manifest.source_acquired_at_utc,
                "buildings_sha256": plateau_prepared.manifest.output_sha256["buildings"],
                "height_provenance": "LOD1 top_z_m minus bottom_z_m",
                "default_height_m": None,
            },
        },
        "buildings": {
            "osm": _building_metrics(osm, osm_heights, osm_manifest.default_building_height_m),
            "plateau": _building_metrics(plateau, plateau_heights, None),
            "count_difference_plateau_minus_osm": len(plateau) - len(osm),
        },
        "footprints": {
            "osm_area_m2": round(osm_union.area, 3),
            "plateau_area_m2": round(plateau_union.area, 3),
            "shared_area_m2": round(shared_area, 3),
            "intersection_over_union": round(shared_area / combined_area, 6) if combined_area else 0.0,
            "osm_covered_by_plateau_pct": round(100 * shared_area / osm_union.area, 3) if osm_union.area else 0.0,
            "plateau_covered_by_osm_pct": round(100 * shared_area / plateau_union.area, 3) if plateau_union.area else 0.0,
        },
        "shadows": {
            "solar_altitude_deg": round(osm_shadow.solar_altitude_deg, 6),
            "solar_azimuth_deg": round(osm_shadow.solar_azimuth_deg, 6),
            "osm_area_m2": round(osm_shadow_geometry.area, 3) if osm_shadow_geometry else 0.0,
            "plateau_area_m2": round(plateau_shadow_geometry.area, 3) if plateau_shadow_geometry else 0.0,
            "shared_area_m2": round(shared_shadow_area, 3),
            "intersection_over_union": round(shared_shadow_area / shadow_union_area, 6) if shadow_union_area else 0.0,
            "osm_covered_by_plateau_pct": round(100 * shared_shadow_area / osm_shadow_geometry.area, 3) if osm_shadow_geometry else 0.0,
            "plateau_covered_by_osm_pct": round(100 * shared_shadow_area / plateau_shadow_geometry.area, 3) if plateau_shadow_geometry else 0.0,
            "osm_polygon_parts": osm_shadow.shadow_polygon_count,
            "plateau_polygon_parts": plateau_shadow.shadow_polygon_count,
        },
        "performance_seconds": {
            "geometry_comparison": round(geometry_seconds, 6),
            "osm_shadow": round(osm_shadow_seconds, 6),
            "plateau_shadow": round(plateau_shadow_seconds, 6),
            "total": round(perf_counter() - started, 6),
        },
        "limitations": [
            "OSM preprocessing replaced missing heights with the default, so the original missing-height rate cannot be reconstructed.",
            "A value equal to 10m in OSM is only an upper bound for defaulted heights because a source height may genuinely be 10m.",
            "Footprint overlap is not a one-to-one building match and does not establish positional truth.",
            "Shadows use the current convex-hull extrusion model; terrain, trees, eaves, and occlusion are excluded.",
        ],
    }


def write_comparison_report(report: dict[str, object], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _clip_buildings(frame: gpd.GeoDataFrame, scope: object) -> gpd.GeoDataFrame:
    selected = frame[frame.geometry.notna() & frame.geometry.intersects(scope)].copy()
    selected["geometry"] = selected.geometry.intersection(scope)
    return selected[
        selected.geometry.geom_type.isin(("Polygon", "MultiPolygon"))
    ].reset_index(drop=True)


def _building_metrics(frame: gpd.GeoDataFrame, heights: pd.Series, default: float | None) -> dict[str, object]:
    valid = heights.dropna()
    result: dict[str, object] = {
        "count": len(frame),
        "height_valid_count": int(valid.size),
        "height_missing_count": int(heights.isna().sum()),
        "height_completion_pct": round(100 * valid.size / len(frame), 3) if len(frame) else 0.0,
        "height_mean_m": round(float(valid.mean()), 3) if not valid.empty else None,
        "height_median_m": round(float(valid.median()), 3) if not valid.empty else None,
        "height_p10_m": round(float(valid.quantile(0.1)), 3) if not valid.empty else None,
        "height_p90_m": round(float(valid.quantile(0.9)), 3) if not valid.empty else None,
    }
    if default is not None:
        result["default_value_count_upper_bound"] = int((valid == default).sum())
        result["default_value_pct_upper_bound"] = round(
            100 * int((valid == default).sum()) / len(frame), 3
        ) if len(frame) else 0.0
    return result


def _calculate_shadow(frame: gpd.GeoDataFrame, height_column: str, manifest: object, config: BuildingComparisonConfig):
    buildings = frame[[height_column, "geometry"]].rename(columns={height_column: "height"})
    buildings = buildings.explode(index_parts=False, ignore_index=True)
    buildings = buildings[buildings.geometry.geom_type == "Polygon"].reset_index(drop=True)
    payload = type("ComparisonPayload", (), {"buildings": buildings, "manifest": manifest})()
    dataset = SpatialDataset(payload, "comparison", "fixed", f"radius={config.radius_m}", str(frame.crs))
    return BuildingShadowCalculator(center=config.center).calculate(dataset, config.departure)
