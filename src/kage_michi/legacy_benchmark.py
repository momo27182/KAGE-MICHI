"""Instrumented version of the hackathon pipeline for baseline measurement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import folium
import networkx as nx
import osmnx as ox
import pandas as pd
from pysolar.solar import get_altitude, get_azimuth
from shapely.geometry import MultiPoint, Point
from shapely.ops import unary_union
from shapely.prepared import prep

from .benchmark_cases import BenchmarkCase, Coordinate
from .performance import PerformanceRecorder


DEFAULT_CENTER = Coordinate(latitude=34.2325, longitude=135.1917)
DEFAULT_RADIUS_M = 1_700
PROJECTED_CRS = "EPSG:6676"


@dataclass
class LegacyDataBundle:
    graph: nx.MultiDiGraph
    projected_graph: nx.MultiDiGraph
    buildings: gpd.GeoDataFrame
    projected_buildings: gpd.GeoDataFrame
    spots: gpd.GeoDataFrame


def distance_m(a: Coordinate, b: Coordinate) -> float:
    """Return great-circle distance using a dependency-free haversine formula."""
    radius = 6_371_008.8
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(b.longitude - a.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(haversine))


def case_is_in_scope(
    case: BenchmarkCase,
    center: Coordinate = DEFAULT_CENTER,
    radius_m: float = DEFAULT_RADIUS_M,
) -> bool:
    return (
        distance_m(center, case.start) <= radius_m
        and distance_m(center, case.destination) <= radius_m
    )


def configure_osmnx_cache(cache_dir: str | Path) -> None:
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cache_dir))


def load_legacy_data(
    recorder: PerformanceRecorder,
    center: Coordinate = DEFAULT_CENTER,
    radius_m: int = DEFAULT_RADIUS_M,
) -> LegacyDataBundle:
    point = (center.latitude, center.longitude)

    with recorder.measure("osm_road_download", radius_m=radius_m):
        graph = ox.graph_from_point(point, dist=radius_m, network_type="walk")

    with recorder.measure("road_largest_component"):
        graph = ox.truncate.largest_component(graph, strongly=True)

    with recorder.measure("osm_building_download", radius_m=radius_m):
        buildings = ox.features_from_point(
            point, tags={"building": True}, dist=radius_m
        )

    with recorder.measure("building_height_normalization"):
        buildings = buildings.copy()
        if "height" not in buildings.columns:
            buildings["height"] = 10.0
        else:
            buildings["height"] = pd.to_numeric(
                buildings["height"], errors="coerce"
            ).fillna(10.0)

    with recorder.measure("osm_spot_download", radius_m=radius_m):
        spots = ox.features_from_point(
            point,
            tags={"shop": "convenience", "amenity": "drinking_water"},
            dist=radius_m,
        )

    with recorder.measure("coordinate_projection"):
        projected_buildings = buildings.to_crs(PROJECTED_CRS)
        projected_graph = ox.project_graph(graph, to_crs=PROJECTED_CRS)

    recorder.metadata.update(
        {
            "road_nodes": graph.number_of_nodes(),
            "road_edges": graph.number_of_edges(),
            "building_features": len(buildings),
            "spot_features": len(spots),
        }
    )
    return LegacyDataBundle(
        graph=graph,
        projected_graph=projected_graph,
        buildings=buildings,
        projected_buildings=projected_buildings,
        spots=spots,
    )


def create_shadow_polygon(
    buildings: gpd.GeoDataFrame,
    case: BenchmarkCase,
    recorder: PerformanceRecorder,
) -> Any | None:
    utc_datetime = case.departure_jst.astimezone(timezone.utc)
    with recorder.measure("solar_position"):
        altitude = get_altitude(
            DEFAULT_CENTER.latitude, DEFAULT_CENTER.longitude, utc_datetime
        )
        azimuth = get_azimuth(
            DEFAULT_CENTER.latitude, DEFAULT_CENTER.longitude, utc_datetime
        )

    recorder.metadata.update(
        {"solar_altitude_deg": altitude, "solar_azimuth_deg": azimuth}
    )
    if altitude <= 0:
        return None

    shadow_len_factor = 1 / math.tan(math.radians(altitude))
    azimuth_math = math.radians(azimuth - 180)
    dx = shadow_len_factor * math.sin(azimuth_math)
    dy = shadow_len_factor * math.cos(azimuth_math)

    polygons = []
    with recorder.measure("shadow_polygon_generation", building_features=len(buildings)):
        for geometry, height in zip(buildings.geometry, buildings["height"]):
            if geometry.geom_type != "Polygon":
                continue
            x, y = geometry.exterior.coords.xy
            ground = list(zip(x, y))
            roof = [
                (x_value + height * dx, y_value + height * dy)
                for x_value, y_value in zip(x, y)
            ]
            polygons.append(MultiPoint(ground + roof).convex_hull)

    if not polygons:
        return None
    with recorder.measure("shadow_union", shadow_polygon_count=len(polygons)):
        merged_shadow = unary_union(polygons).simplify(0.5)
    recorder.metadata["shadow_polygon_count"] = len(polygons)
    return merged_shadow


def solve_route(
    bundle: LegacyDataBundle,
    case: BenchmarkCase,
    shadows: Any | None,
    recorder: PerformanceRecorder,
) -> tuple[dict[str, float], list[int]] | None:
    with recorder.measure("nearest_node_lookup"):
        origin = ox.distance.nearest_nodes(
            bundle.graph, X=case.start.longitude, Y=case.start.latitude
        )
        destination = ox.distance.nearest_nodes(
            bundle.graph,
            X=case.destination.longitude,
            Y=case.destination.latitude,
        )

    prepared_shadows = prep(shadows) if shadows is not None else None
    shaded_edge_count = 0
    with recorder.measure(
        "road_shade_classification", road_edges=bundle.projected_graph.number_of_edges()
    ):
        for u, v, _, data in bundle.projected_graph.edges(keys=True, data=True):
            length = data["length"]
            if "geometry" in data:
                midpoint = data["geometry"].interpolate(0.5, normalized=True)
            else:
                first = bundle.projected_graph.nodes[u]
                second = bundle.projected_graph.nodes[v]
                midpoint = Point(
                    (first["x"] + second["x"]) / 2,
                    (first["y"] + second["y"]) / 2,
                )
            is_shaded = bool(
                prepared_shadows is not None and prepared_shadows.contains(midpoint)
            )
            data["is_shaded"] = is_shaded
            data["shadow_cost"] = (
                length if is_shaded else length * case.sun_penalty
            )
            shaded_edge_count += int(is_shaded)

    recorder.metadata["shaded_edge_count"] = shaded_edge_count
    with recorder.measure("route_search"):
        try:
            route = nx.shortest_path(
                bundle.projected_graph,
                origin,
                destination,
                weight="shadow_cost",
            )
        except nx.NetworkXNoPath:
            return None
    if len(route) < 2:
        return None

    total_distance = 0.0
    sunny_distance = 0.0
    with recorder.measure("route_metrics"):
        for u, v in zip(route[:-1], route[1:]):
            edge = min(
                bundle.projected_graph[u][v].values(),
                key=lambda value: value["length"],
            )
            distance = float(edge["length"])
            total_distance += distance
            if not edge.get("is_shaded", False):
                sunny_distance += distance

    return (
        {
            "route_distance_m": total_distance,
            "walk_minutes": math.ceil(total_distance / 80),
            "shade_ratio_pct": (
                100 * (1 - sunny_distance / total_distance) if total_distance else 0
            ),
            "sunny_distance_m": sunny_distance,
        },
        route,
    )


def render_route_map(
    bundle: LegacyDataBundle,
    case: BenchmarkCase,
    shadows: Any | None,
    route: list[int],
    recorder: PerformanceRecorder,
) -> int:
    """Build the same major Folium layers as the hackathon app and render HTML."""
    with recorder.measure("folium_map_generation"):
        map_object = folium.Map(
            location=[DEFAULT_CENTER.latitude, DEFAULT_CENTER.longitude],
            zoom_start=15,
            tiles="CartoDB positron",
        )
        if shadows is not None:
            shadow_frame = gpd.GeoDataFrame(
                geometry=[shadows], crs=bundle.projected_buildings.crs
            ).to_crs(epsg=4326)
            folium.GeoJson(
                shadow_frame,
                style_function=lambda _: {
                    "fillColor": "#404040",
                    "color": "none",
                    "fillOpacity": 0.3,
                },
            ).add_to(map_object)

        for _, spot in bundle.spots.iterrows():
            geometry = spot.geometry
            location = (
                [geometry.y, geometry.x]
                if geometry.geom_type == "Point"
                else [geometry.centroid.y, geometry.centroid.x]
            )
            folium.Marker(location).add_to(map_object)

        folium.Marker(
            [case.start.latitude, case.start.longitude], tooltip="Start"
        ).add_to(map_object)
        folium.Marker(
            [case.destination.latitude, case.destination.longitude], tooltip="Goal"
        ).add_to(map_object)
        route_coordinates = [
            (bundle.graph.nodes[node]["y"], bundle.graph.nodes[node]["x"])
            for node in route
        ]
        folium.PolyLine(route_coordinates, color="#8090C0", weight=6).add_to(
            map_object
        )

    with recorder.measure("folium_html_render"):
        html = map_object.get_root().render()
    recorder.metadata["map_html_bytes"] = len(html.encode("utf-8"))
    return recorder.metadata["map_html_bytes"]
