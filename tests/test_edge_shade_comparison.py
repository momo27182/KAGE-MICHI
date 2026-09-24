from pathlib import Path
import sys
import unittest

import networkx as nx
from shapely.geometry import LineString, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.edge_shade_comparison import compare_edge_shade_methods


class EdgeShadeComparisonTests(unittest.TestCase):
    def test_reports_accuracy_time_and_storage(self) -> None:
        graph = nx.MultiDiGraph(crs="EPSG:6676")
        graph.add_node(1, x=0.0, y=0.0)
        graph.add_node(2, x=20.0, y=0.0)
        graph.add_edge(1, 2, length=20.0, geometry=LineString([(0, 0), (20, 0)]))
        shadow = Polygon([(0, -1), (7, -1), (7, 1), (0, 1)])

        report = compare_edge_shade_methods(graph, shadow, (5.0, 10.0))

        self.assertEqual(report["edge_count"], 1)
        self.assertEqual(report["methods"]["intersection_length"]["mean_shade_ratio"], 0.35)
        self.assertIn("mean_absolute_error", report["methods"]["sample_5m"])
        self.assertEqual(report["storage_estimate"]["float32_bytes_per_time_slice"], 4)
        self.assertGreater(report["storage_estimate"]["float32_mib_for_24h_at_5min"], 0)


if __name__ == "__main__":
    unittest.main()
