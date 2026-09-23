"""Convert prepared OSM spots into small, UI-ready facility markers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import geopandas as gpd
import pandas as pd


FacilityKind = Literal["convenience", "drinking_water"]


@dataclass(frozen=True)
class FacilityMarker:
    kind: FacilityKind
    name: str
    latitude: float
    longitude: float


def prepare_facility_markers(spots: gpd.GeoDataFrame) -> tuple[FacilityMarker, ...]:
    """Normalize optional attributes and geometry without contacting OSM."""
    if spots.empty or spots.crs is None:
        return ()

    rows: list[tuple[FacilityKind, str, object]] = []
    for _, spot in spots.iterrows():
        geometry = spot.get("geometry")
        if geometry is None or geometry.is_empty:
            continue
        kinds: list[FacilityKind] = []
        if _text(spot.get("shop")) == "convenience":
            kinds.append("convenience")
        if _text(spot.get("amenity")) == "drinking_water":
            kinds.append("drinking_water")
        name = _facility_name(spot)
        for kind in kinds:
            rows.append((kind, name, geometry.representative_point()))

    if not rows:
        return ()

    points = gpd.GeoSeries([row[2] for row in rows], crs=spots.crs).to_crs("EPSG:4326")
    return tuple(
        FacilityMarker(kind, name, point.y, point.x)
        for (kind, name, _), point in zip(rows, points)
    )


def _facility_name(spot: pd.Series) -> str:
    for key in ("name:ja", "name", "brand:ja", "brand"):
        value = _text(spot.get(key))
        if value:
            return value
    return "名称未登録"


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()
