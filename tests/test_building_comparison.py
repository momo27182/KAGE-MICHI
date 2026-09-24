from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.building_comparison import (
    BuildingComparisonConfig,
    compare_prepared_buildings,
    write_comparison_report,
)
from kage_michi.models import GeoPoint


class BuildingComparisonTests(unittest.TestCase):
    departure = datetime(2026, 8, 11, 14, 0, tzinfo=timezone(timedelta(hours=9)))

    def fixtures(self):
        x, y = -304_834.0, -191_118.0
        osm = gpd.GeoDataFrame(
            {"height": [10.0, 20.0]},
            geometry=[
                Polygon([(x, y), (x + 10, y), (x + 10, y + 10), (x, y + 10)]),
                Polygon([(x + 20, y), (x + 30, y), (x + 30, y + 10), (x + 20, y + 10)]),
            ],
            crs="EPSG:6676",
        )
        plateau = gpd.GeoDataFrame(
            {"height_m": [12.0, None]},
            geometry=[
                Polygon([(x, y), (x + 10, y), (x + 10, y + 10), (x, y + 10)]),
                Polygon([(x + 40, y), (x + 50, y), (x + 50, y + 10), (x + 40, y + 10)]),
            ],
            crs="EPSG:6676",
        )
        osm_manifest = SimpleNamespace(
            acquired_at_utc="2026-01-01T00:00:00+00:00",
            sha256={"buildings": "osm-sha"},
            default_building_height_m=10.0,
        )
        plateau_manifest = SimpleNamespace(
            source_acquired_at_utc="2026-01-02T00:00:00+00:00",
            output_sha256={"buildings": "plateau-sha"},
        )
        return osm, osm_manifest, SimpleNamespace(buildings=plateau, manifest=plateau_manifest)

    def test_compares_counts_heights_footprints_and_shadows(self) -> None:
        fixtures = self.fixtures()
        config = BuildingComparisonConfig(GeoPoint(34.2325, 135.1917), 1000, self.departure)
        with patch(
            "kage_michi.infrastructure.building_comparison.load_prepared_buildings",
            return_value=fixtures[:2],
        ), patch(
            "kage_michi.infrastructure.building_comparison.load_prepared_plateau_buildings",
            return_value=fixtures[2],
        ):
            report = compare_prepared_buildings("osm", "plateau", config)

        self.assertEqual(report["buildings"]["osm"]["count"], 2)
        self.assertEqual(report["buildings"]["plateau"]["height_missing_count"], 1)
        self.assertEqual(report["buildings"]["osm"]["default_value_count_upper_bound"], 1)
        self.assertAlmostEqual(report["footprints"]["intersection_over_union"], 1 / 3, places=6)
        self.assertGreater(report["shadows"]["osm_area_m2"], 0)
        self.assertIn("cannot be reconstructed", report["limitations"][0])

    def test_requires_timezone_and_writes_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            BuildingComparisonConfig(GeoPoint(0, 129), 100, datetime(2026, 1, 1))
        with tempfile.TemporaryDirectory() as directory:
            path = write_comparison_report({"schema_version": 1}, Path(directory) / "report.json")
            self.assertEqual(json.loads(path.read_text("utf-8"))["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
