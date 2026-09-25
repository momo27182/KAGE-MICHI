"""Route planning from validated, time-indexed shade ratios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import networkx as nx
import osmnx as ox
from pyproj import Transformer

from ..data import SpatialDataset
from ..models import GeoPoint, RouteComparison, RouteResult
from ..routing import RouteNotFoundError
from .precomputed_shade import PreparedShadeRatios
from .shade_route_planner import MidpointShadeRoutePlanner


class ShadeTimeUnavailableError(ValueError):
    """Raised when the artifact does not contain the requested time slot."""


@dataclass(frozen=True)
class ResolvedShadeTime:
    requested: datetime
    resolved: datetime
    index: int
    daylight: bool
    solar_altitude_deg: float


def resolve_shade_time(
    prepared: PreparedShadeRatios, requested: datetime
) -> ResolvedShadeTime:
    """Resolve to the latest completed interval, never to a future time slot."""
    if requested.utcoffset() is None:
        raise ValueError("requested shade time must include timezone information")
    zone = ZoneInfo(prepared.manifest.timezone)
    local = requested.astimezone(zone)
    interval = prepared.manifest.interval_minutes
    minute = local.minute - local.minute % interval
    resolved = local.replace(minute=minute, second=0, microsecond=0)
    key = resolved.isoformat()
    try:
        index = prepared.timestamps.index(key)
    except ValueError as error:
        raise ShadeTimeUnavailableError(
            f"事前計算済み日陰率がありません: {key}"
        ) from error
    return ResolvedShadeTime(
        requested=requested,
        resolved=resolved,
        index=index,
        daylight=bool(prepared.daylight[index]),
        solar_altitude_deg=float(prepared.solar_altitude_deg[index]),
    )


@dataclass(frozen=True)
class PrecomputedShadeRoutePlanner:
    sun_penalty: float = 10.0

    def __post_init__(self) -> None:
        if self.sun_penalty < 1:
            raise ValueError("sun_penalty must be at least 1")

    def compare_routes(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        prepared: PreparedShadeRatios,
        departure: datetime,
    ) -> tuple[RouteComparison, ResolvedShadeTime]:
        graph, origin, target, resolved = self._prepare_graph(
            dataset, start, destination, prepared, departure
        )
        return (
            RouteComparison(
                shortest=MidpointShadeRoutePlanner._route_result(
                    graph, origin, target, "length"
                ),
                shade_optimized=MidpointShadeRoutePlanner._route_result(
                    graph, origin, target, "shade_cost"
                ),
            ),
            resolved,
        )

    def _prepare_graph(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        prepared: PreparedShadeRatios,
        departure: datetime,
    ) -> tuple[nx.MultiDiGraph, int, int, ResolvedShadeTime]:
        graph = dataset.payload.graph.copy()
        crs = graph.graph.get("crs")
        if crs is None:
            raise ValueError("route graph must define a CRS")
        if str(crs) != prepared.manifest.projected_crs:
            raise ValueError("shade artifact and route graph CRS mismatch")

        graph_edges = {
            (str(u), str(v), str(key)): (u, v, key)
            for u, v, key in graph.edges(keys=True)
        }
        if len(graph_edges) != graph.number_of_edges():
            raise ValueError("route graph contains duplicate stable edge keys")
        artifact_edges = tuple(
            zip(prepared.edge_u, prepared.edge_v, prepared.edge_key)
        )
        artifact_set = set(artifact_edges)
        graph_set = set(graph_edges)
        missing = graph_set - artifact_set
        extra = artifact_set - graph_set
        if missing or extra:
            raise ValueError(
                "shade artifact edge keys do not match route graph "
                f"(missing={len(missing)}, extra={len(extra)})"
            )

        resolved = resolve_shade_time(prepared, departure)
        ratios = prepared.ratios[resolved.index]
        for identity, ratio in zip(artifact_edges, ratios):
            u, v, key = graph_edges[identity]
            edge = graph[u][v][key]
            length = float(edge["length"])
            value = float(ratio)
            edge["shade_ratio"] = value
            edge["is_shaded"] = value >= 0.5
            edge["shade_cost"] = length * (
                1.0 + (self.sun_penalty - 1.0) * (1.0 - value)
            )

        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        start_x, start_y = transformer.transform(start.longitude, start.latitude)
        destination_x, destination_y = transformer.transform(
            destination.longitude, destination.latitude
        )
        origin = ox.distance.nearest_nodes(graph, X=start_x, Y=start_y)
        target = ox.distance.nearest_nodes(graph, X=destination_x, Y=destination_y)
        if origin == target:
            raise RouteNotFoundError("start and destination resolve to the same node")
        return graph, int(origin), int(target), resolved
