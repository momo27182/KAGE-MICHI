"""Concrete building-shadow calculation separated from routing and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math

import pandas as pd
from pysolar.solar import get_altitude, get_azimuth
from shapely.geometry import MultiPoint
from shapely.ops import unary_union

from ..data import SpatialDataset
from ..models import GeoPoint
from ..shadows import ShadowResult, SolarPosition, SolarPositionProvider


@dataclass(frozen=True)
class PysolarPositionProvider:
    def position(self, point: GeoPoint, at: datetime) -> SolarPosition:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("shadow datetime must include timezone information")
        utc_datetime = at.astimezone(timezone.utc)
        return SolarPosition(
            altitude_deg=get_altitude(point.latitude, point.longitude, utc_datetime),
            azimuth_deg=get_azimuth(point.latitude, point.longitude, utc_datetime),
        )


@dataclass(frozen=True)
class BuildingShadowCalculator:
    center: GeoPoint
    solar_provider: SolarPositionProvider = field(
        default_factory=PysolarPositionProvider
    )
    default_height_m: float = 10.0
    simplify_tolerance_m: float = 0.5

    def __post_init__(self) -> None:
        if self.default_height_m <= 0:
            raise ValueError("default_height_m must be positive")
        if self.simplify_tolerance_m < 0:
            raise ValueError("simplify_tolerance_m must not be negative")

    def calculate(self, dataset: SpatialDataset, departure: datetime) -> ShadowResult:
        position = self.solar_provider.position(self.center, departure)
        buildings = dataset.payload.buildings
        building_count = len(buildings)
        if position.altitude_deg <= 0:
            return ShadowResult(
                geometry=None,
                solar_altitude_deg=position.altitude_deg,
                solar_azimuth_deg=position.azimuth_deg,
                building_count=building_count,
            )

        default_height = getattr(
            getattr(dataset.payload, "manifest", None),
            "default_building_height_m",
            self.default_height_m,
        )
        if "height" in buildings.columns:
            heights = pd.to_numeric(buildings["height"], errors="coerce").fillna(
                default_height
            )
        else:
            heights = pd.Series(default_height, index=buildings.index)

        factor = 1 / math.tan(math.radians(position.altitude_deg))
        direction = math.radians(position.azimuth_deg - 180)
        dx = factor * math.sin(direction)
        dy = factor * math.cos(direction)
        polygons = []
        for geometry, height in zip(buildings.geometry, heights):
            if geometry is None or geometry.is_empty or geometry.geom_type != "Polygon":
                continue
            ground = list(geometry.exterior.coords)
            roof = [
                (x + float(height) * dx, y + float(height) * dy)
                for x, y in geometry.exterior.coords
            ]
            polygons.append(MultiPoint(ground + roof).convex_hull)

        merged = (
            unary_union(polygons).simplify(self.simplify_tolerance_m)
            if polygons
            else None
        )
        return ShadowResult(
            geometry=merged,
            solar_altitude_deg=position.altitude_deg,
            solar_azimuth_deg=position.azimuth_deg,
            building_count=building_count,
            shadow_polygon_count=len(polygons),
        )
