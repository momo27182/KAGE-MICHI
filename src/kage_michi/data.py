"""Boundary for obtaining prepared spatial data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import GeoPoint


@dataclass(frozen=True)
class SpatialDataset:
    """Opaque prepared data with the metadata required for traceability."""

    payload: object
    source: str
    acquired_at: str
    scope: str
    crs: str


class SpatialDataSource(Protocol):
    def load(self, start: GeoPoint, destination: GeoPoint) -> SpatialDataset:
        """Return prepared data covering both points without defining storage here."""
