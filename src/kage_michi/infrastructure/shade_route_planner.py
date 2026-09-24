"""Concrete midpoint-based shade routing separated from shadow generation."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import osmnx as ox
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point
from shapely.prepared import prep

from ..data import SpatialDataset
from ..models import GeoPoint, RouteComparison, RouteResult
from ..routing import RouteNotFoundError
from ..shadows import ShadowResult
from .edge_shade import sampled_shade_ratio


@dataclass(frozen=True)
class MidpointShadeRoutePlanner:
    sun_penalty: float = 10.0

    def __post_init__(self) -> None:
        if self.sun_penalty < 1:
            raise ValueError("sun_penalty must be at least 1")

    def find_route(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        shadows: ShadowResult,
    ) -> RouteResult:
        graph, origin, target = self._prepare_graph(
            dataset, start, destination, shadows
        )
        return self._route_result(graph, origin, target, "shade_cost")

    def compare_routes(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        shadows: ShadowResult,
    ) -> RouteComparison:
        """Calculate both routes after classifying every edge only once."""
        graph, origin, target = self._prepare_graph(
            dataset, start, destination, shadows
        )
        return RouteComparison(
            shortest=self._route_result(graph, origin, target, "length"),
            shade_optimized=self._route_result(
                graph, origin, target, "shade_cost"
            ),
        )

    def _prepare_graph(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        shadows: ShadowResult,
    ) -> tuple[nx.MultiDiGraph, int, int]:
        graph = dataset.payload.graph.copy()
        crs = graph.graph.get("crs")
        if crs is None:
            raise ValueError("route graph must define a CRS")
        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        start_x, start_y = transformer.transform(start.longitude, start.latitude)
        destination_x, destination_y = transformer.transform(
            destination.longitude, destination.latitude
        )
        origin = ox.distance.nearest_nodes(graph, X=start_x, Y=start_y)
        target = ox.distance.nearest_nodes(
            graph, X=destination_x, Y=destination_y
        )
        if origin == target:
            raise RouteNotFoundError("start and destination resolve to the same node")

        prepared_shadows = prep(shadows.geometry) if shadows.geometry is not None else None
        for u, v, _, edge in graph.edges(keys=True, data=True):
            length = float(edge["length"])
            geometry = edge.get("geometry")
            if geometry is None:
                first = graph.nodes[u]
                second = graph.nodes[v]
                midpoint = Point(
                    (float(first["x"]) + float(second["x"])) / 2,
                    (float(first["y"]) + float(second["y"])) / 2,
                )
            else:
                midpoint = geometry.interpolate(0.5, normalized=True)
            is_shaded = bool(
                prepared_shadows is not None and prepared_shadows.contains(midpoint)
            )
            edge["is_shaded"] = is_shaded
            edge["shade_ratio"] = 1.0 if is_shaded else 0.0
            edge["shade_cost"] = length if is_shaded else length * self.sun_penalty

        return graph, int(origin), int(target)

    @staticmethod
    def _route_result(
        graph: nx.MultiDiGraph, origin: int, target: int, weight: str
    ) -> RouteResult:
        try:
            route = nx.shortest_path(graph, origin, target, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound) as error:
            raise RouteNotFoundError("no walking route connects the requested points") from error
        if len(route) < 2:
            raise RouteNotFoundError("route contains fewer than two nodes")

        total_distance = 0.0
        sunny_distance = 0.0
        for u, v in zip(route[:-1], route[1:]):
            edge = min(
                graph[u][v].values(),
                key=lambda value: float(value[weight]),
            )
            length = float(edge["length"])
            total_distance += length
            shade_ratio = float(
                edge.get("shade_ratio", 1.0 if edge.get("is_shaded") else 0.0)
            )
            sunny_distance += length * (1.0 - shade_ratio)
        return RouteResult(
            node_ids=tuple(int(node) for node in route),
            distance_m=total_distance,
            sunny_distance_m=sunny_distance,
        )


@dataclass(frozen=True)
class SampledShadeRoutePlanner(MidpointShadeRoutePlanner):
    """Route planner using a continuous shade ratio for each road edge."""

    sample_spacing_m: float = 5.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.sample_spacing_m <= 0:
            raise ValueError("sample_spacing_m must be positive")

    def _prepare_graph(
        self,
        dataset: SpatialDataset,
        start: GeoPoint,
        destination: GeoPoint,
        shadows: ShadowResult,
    ) -> tuple[nx.MultiDiGraph, int, int]:
        graph = dataset.payload.graph.copy()
        crs = graph.graph.get("crs")
        if crs is None:
            raise ValueError("route graph must define a CRS")
        if not CRS.from_user_input(crs).is_projected:
            raise ValueError("sampled shade routing requires a projected CRS")

        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        start_x, start_y = transformer.transform(start.longitude, start.latitude)
        destination_x, destination_y = transformer.transform(
            destination.longitude, destination.latitude
        )
        origin = ox.distance.nearest_nodes(graph, X=start_x, Y=start_y)
        target = ox.distance.nearest_nodes(graph, X=destination_x, Y=destination_y)
        if origin == target:
            raise RouteNotFoundError("start and destination resolve to the same node")

        for u, v, _, edge in graph.edges(keys=True, data=True):
            length = float(edge["length"])
            geometry = edge.get("geometry")
            if geometry is None:
                first = graph.nodes[u]
                second = graph.nodes[v]
                geometry = LineString(
                    [
                        (float(first["x"]), float(first["y"])),
                        (float(second["x"]), float(second["y"])),
                    ]
                )
            ratio, sample_count = sampled_shade_ratio(
                geometry, shadows.geometry, self.sample_spacing_m
            )
            edge["shade_ratio"] = ratio
            edge["shade_sample_count"] = sample_count
            edge["is_shaded"] = ratio >= 0.5
            edge["shade_cost"] = length * (
                1.0 + (self.sun_penalty - 1.0) * (1.0 - ratio)
            )

        return graph, int(origin), int(target)
