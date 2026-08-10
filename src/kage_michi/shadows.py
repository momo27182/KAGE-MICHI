"""Boundary for shadow calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .data import SpatialDataset


@dataclass(frozen=True)
class ShadowResult:
    geometry: object | None
    solar_altitude_deg: float
    solar_azimuth_deg: float


class ShadowCalculator(Protocol):
    def calculate(self, dataset: SpatialDataset, departure: datetime) -> ShadowResult:
        """Calculate shadows for one prepared dataset and time."""
