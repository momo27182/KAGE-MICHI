"""Boundary for shadow calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .data import SpatialDataset
from .models import GeoPoint


@dataclass(frozen=True)
class SolarPosition:
    altitude_deg: float
    azimuth_deg: float


class SolarPositionProvider(Protocol):
    def position(self, point: GeoPoint, at: datetime) -> SolarPosition:
        """Return the sun position for one point and timezone-aware datetime."""


@dataclass(frozen=True)
class ShadowResult:
    geometry: object | None
    solar_altitude_deg: float
    solar_azimuth_deg: float
    building_count: int = 0
    shadow_polygon_count: int = 0


class ShadowCalculator(Protocol):
    def calculate(self, dataset: SpatialDataset, departure: datetime) -> ShadowResult:
        """Calculate shadows for one prepared dataset and time."""
