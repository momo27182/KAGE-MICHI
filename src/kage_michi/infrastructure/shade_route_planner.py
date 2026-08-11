"""Concrete midpoint-based shade routing separated from shadow generation."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import Point
from shapely.prepared import prep

from ..data import SpatialDataset
from ..models import GeoPoint, RouteResult
from ..routing import RouteNotFoundError
from ..shadows import ShadowResult


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
            edge["shade_cost"] = length if is_shaded else length * self.sun_penalty

        try:
            route = nx.shortest_path(graph, origin, target, weight="shade_cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound) as error:
            raise RouteNotFoundError("no walking route connects the requested points") from error
        if len(route) < 2:
            raise RouteNotFoundError("route contains fewer than two nodes")

        total_distance = 0.0
        sunny_distance = 0.0
        for u, v in zip(route[:-1], route[1:]):
            edge = min(
                graph[u][v].values(),
                key=lambda value: float(value["shade_cost"]),
            )
            length = float(edge["length"])
            total_distance += length
            if not edge["is_shaded"]:
                sunny_distance += length
        return RouteResult(
            node_ids=tuple(int(node) for node in route),
            distance_m=total_distance,
            sunny_distance_m=sunny_distance,
        )
