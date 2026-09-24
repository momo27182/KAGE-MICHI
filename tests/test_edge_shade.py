from pathlib import Path
import sys
import unittest

from shapely.geometry import LineString, MultiLineString, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.edge_shade import (
    intersection_shade_ratio,
    normalize_edge_geometry,
    sampled_shade_ratio,
)


class EdgeShadeTests(unittest.TestCase):
    line = LineString([(0, 0), (20, 0)])

    def test_partial_shade_is_measured_as_ratio(self) -> None:
        shadow = Polygon([(0, -1), (10, -1), (10, 1), (0, 1)])

        ratio, samples = sampled_shade_ratio(self.line, shadow, spacing_m=5)

        self.assertEqual(samples, 4)
        self.assertEqual(ratio, 0.5)
        self.assertEqual(intersection_shade_ratio(self.line, shadow), 0.5)

    def test_empty_and_complete_shadows(self) -> None:
        complete = Polygon([(-1, -1), (21, -1), (21, 1), (-1, 1)])

        self.assertEqual(sampled_shade_ratio(self.line, None, 10), (0.0, 2))
        self.assertEqual(sampled_shade_ratio(self.line, complete, 10), (1.0, 2))
        self.assertEqual(intersection_shade_ratio(self.line, None), 0.0)
        self.assertEqual(intersection_shade_ratio(self.line, complete), 1.0)

    def test_sampling_error_is_bounded_by_one_bin_for_simple_boundary(self) -> None:
        shadow = Polygon([(0, -1), (7, -1), (7, 1), (0, 1)])

        sampled, sample_count = sampled_shade_ratio(self.line, shadow, spacing_m=5)
        exact = intersection_shade_ratio(self.line, shadow)

        self.assertLessEqual(abs(sampled - exact), 1 / sample_count)

    def test_spacing_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            sampled_shade_ratio(self.line, None, 0)

    def test_rejects_disconnected_multiline(self) -> None:
        line = MultiLineString([[(0, 0), (1, 0)], [(2, 0), (3, 0)]])

        with self.assertRaisesRegex(ValueError, "continuous line"):
            normalize_edge_geometry(line)


if __name__ == "__main__":
    unittest.main()
