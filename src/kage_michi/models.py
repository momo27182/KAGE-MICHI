"""Dependency-free product models shared across KAGE-MICHI modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")


@dataclass(frozen=True)
class RouteRequest:
    start: GeoPoint
    destination: GeoPoint
    departure: datetime
    temperature_c: float | None = None

    def __post_init__(self) -> None:
        if self.departure.tzinfo is None or self.departure.utcoffset() is None:
            raise ValueError("departure must include timezone information")


@dataclass(frozen=True)
class RouteResult:
    node_ids: tuple[int, ...]
    distance_m: float
    sunny_distance_m: float

    @property
    def shade_ratio_pct(self) -> float:
        if self.distance_m <= 0:
            return 0.0
        return 100 * (1 - self.sunny_distance_m / self.distance_m)


@dataclass(frozen=True)
class HeatAssessment:
    level: str
    explanation: str


@dataclass(frozen=True)
class PlannedJourney:
    route: RouteResult
    heat: HeatAssessment | None
