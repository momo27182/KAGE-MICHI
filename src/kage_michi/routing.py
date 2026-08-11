"""Boundary for shade-aware route search."""

from __future__ import annotations

from typing import Protocol

from .data import SpatialDataset
from .models import GeoPoint, RouteResult
from .shadows import ShadowResult


class RouteNotFoundError(RuntimeError):
    """Raised when the prepared graph cannot connect the requested points."""


class RoutePlanner(Protocol):
    def find_route(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        shadows: ShadowResult,
    ) -> RouteResult:
        """Find a walking route using prepared data and calculated shadows."""
