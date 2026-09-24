from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import networkx as nx
from shapely.geometry import LineString, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.data import SpatialDataset
from kage_michi.infrastructure.shade_route_planner import (
    MidpointShadeRoutePlanner,
    SampledShadeRoutePlanner,
)
from kage_michi.models import GeoPoint
from kage_michi.routing import RouteNotFoundError
from kage_michi.shadows import ShadowResult


def make_dataset(connected: bool = True) -> SpatialDataset:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.001)
    graph.add_node(3, x=0.002, y=0.0)
    if connected:
        graph.add_edge(1, 3, length=10.0, geometry=LineString([(0, 0), (0.002, 0)]))
        graph.add_edge(1, 2, length=6.0)
        graph.add_edge(2, 3, length=6.0)
    return SpatialDataset(SimpleNamespace(graph=graph), "test", "fixed", "unit", "EPSG:4326")


def make_shadows() -> ShadowResult:
    return ShadowResult(
        geometry=Polygon([(-1, 0.0001), (1, 0.0001), (1, 1), (-1, 1)]),
        solar_altitude_deg=45.0,
        solar_azimuth_deg=180.0,
    )


class MidpointShadeRoutePlannerTests(unittest.TestCase):
    start = GeoPoint(0.0, 0.0)
    destination = GeoPoint(0.0, 0.002)

    def test_prefers_shaded_detour_using_edge_midpoints(self) -> None:
        result = MidpointShadeRoutePlanner(sun_penalty=10).find_route(
            make_dataset(), self.start, self.destination, make_shadows()
        )

        self.assertEqual(result.node_ids, (1, 2, 3))
        self.assertEqual(result.distance_m, 12.0)
        self.assertEqual(result.sunny_distance_m, 0.0)
        self.assertEqual(result.shade_ratio_pct, 100.0)

    def test_compares_shortest_and_shade_routes_from_one_classification(self) -> None:
        comparison = MidpointShadeRoutePlanner(sun_penalty=10).compare_routes(
            make_dataset(), self.start, self.destination, make_shadows()
        )

        self.assertEqual(comparison.shortest.node_ids, (1, 3))
        self.assertEqual(comparison.shortest.distance_m, 10.0)
        self.assertEqual(comparison.shortest.sunny_distance_m, 10.0)
        self.assertEqual(comparison.shade_optimized.node_ids, (1, 2, 3))
        self.assertEqual(comparison.distance_increase_m, 2.0)
        self.assertEqual(comparison.shade_improvement_points, 100.0)
        self.assertEqual(comparison.walk_time_increase_minutes, 0)

    def test_comparison_allows_both_choices_to_be_the_same_route(self) -> None:
        comparison = MidpointShadeRoutePlanner(sun_penalty=1).compare_routes(
            make_dataset(), self.start, self.destination, make_shadows()
        )

        self.assertEqual(comparison.shortest, comparison.shade_optimized)
        self.assertEqual(comparison.distance_increase_m, 0.0)
        self.assertEqual(comparison.shade_improvement_points, 0.0)

    def test_no_connected_route_raises_domain_error(self) -> None:
        with self.assertRaisesRegex(RouteNotFoundError, "no walking route"):
            MidpointShadeRoutePlanner().find_route(
                make_dataset(connected=False),
                self.start,
                self.destination,
                make_shadows(),
            )

    def test_fixed_input_reproduces_same_route(self) -> None:
        planner = MidpointShadeRoutePlanner(sun_penalty=10)
        dataset = make_dataset()
        shadows = make_shadows()

        first = planner.find_route(dataset, self.start, self.destination, shadows)
        second = planner.find_route(dataset, self.start, self.destination, shadows)

        self.assertEqual(first, second)

class SampledShadeRoutePlannerTests(unittest.TestCase):
    start = GeoPoint(0.0, 0.0)
    destination = GeoPoint(0.0, 0.002)

    def make_dataset(self) -> SpatialDataset:
        graph = nx.MultiDiGraph(crs="EPSG:3857")
        graph.add_node(1, x=0.0, y=0.0)
        graph.add_node(2, x=20.0, y=0.0)
        graph.add_edge(1, 2, length=20.0, geometry=LineString([(0, 0), (20, 0)]))
        return SpatialDataset(
            SimpleNamespace(graph=graph), "test", "fixed", "unit", "EPSG:3857"
        )

    def test_partial_shade_contributes_partial_sunny_distance(self) -> None:
        shadow = ShadowResult(
            geometry=Polygon([(0, -1), (10, -1), (10, 1), (0, 1)]),
            solar_altitude_deg=45.0,
            solar_azimuth_deg=180.0,
        )
        planner = SampledShadeRoutePlanner(sun_penalty=10, sample_spacing_m=5)

        result = planner.find_route(
            self.make_dataset(), GeoPoint(0, 0), GeoPoint(0, 0.00018), shadow
        )

        self.assertEqual(result.distance_m, 20.0)
        self.assertEqual(result.sunny_distance_m, 10.0)
        self.assertEqual(result.shade_ratio_pct, 50.0)

    def test_requires_projected_graph(self) -> None:
        with self.assertRaisesRegex(ValueError, "projected CRS"):
            SampledShadeRoutePlanner().find_route(
                make_dataset(), self.start, self.destination, make_shadows()
            )

    def test_spacing_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            SampledShadeRoutePlanner(sample_spacing_m=0)


if __name__ == "__main__":
    unittest.main()
