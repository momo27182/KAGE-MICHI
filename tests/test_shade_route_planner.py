from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import networkx as nx
from shapely.geometry import LineString, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.data import SpatialDataset
from kage_michi.infrastructure.shade_route_planner import MidpointShadeRoutePlanner
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


if __name__ == "__main__":
    unittest.main()
