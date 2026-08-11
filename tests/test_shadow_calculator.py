from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import geopandas as gpd
from shapely.geometry import Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.data import SpatialDataset
from kage_michi.infrastructure.shadow_calculator import BuildingShadowCalculator
from kage_michi.models import GeoPoint
from kage_michi.shadows import SolarPosition


class FixedSolarPositionProvider:
    def __init__(self, altitude_deg: float, azimuth_deg: float) -> None:
        self.position_value = SolarPosition(altitude_deg, azimuth_deg)

    def position(self, point: GeoPoint, at: datetime) -> SolarPosition:
        return self.position_value


def make_dataset() -> SpatialDataset:
    buildings = gpd.GeoDataFrame(
        {"height": [None]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        crs="EPSG:6676",
    )
    payload = SimpleNamespace(buildings=buildings, manifest=None)
    return SpatialDataset(payload, "test", "fixed", "unit", "EPSG:6676")


class BuildingShadowCalculatorTests(unittest.TestCase):
    departure = datetime(
        2026, 8, 11, 12, 0, tzinfo=timezone(timedelta(hours=9))
    )

    def test_sun_below_horizon_returns_no_shadow(self) -> None:
        calculator = BuildingShadowCalculator(
            center=GeoPoint(34.2325, 135.1917),
            solar_provider=FixedSolarPositionProvider(-1.0, 180.0),
        )

        result = calculator.calculate(make_dataset(), self.departure)

        self.assertIsNone(result.geometry)
        self.assertEqual(result.building_count, 1)
        self.assertEqual(result.shadow_polygon_count, 0)

    def test_missing_height_uses_ten_metre_default(self) -> None:
        calculator = BuildingShadowCalculator(
            center=GeoPoint(34.2325, 135.1917),
            solar_provider=FixedSolarPositionProvider(45.0, 180.0),
            simplify_tolerance_m=0,
        )

        result = calculator.calculate(make_dataset(), self.departure)

        self.assertEqual(result.building_count, 1)
        self.assertEqual(result.shadow_polygon_count, 1)
        self.assertEqual(tuple(round(value, 6) for value in result.geometry.bounds), (0, 0, 1, 11))

    def test_fixed_input_reproduces_same_shadow(self) -> None:
        calculator = BuildingShadowCalculator(
            center=GeoPoint(34.2325, 135.1917),
            solar_provider=FixedSolarPositionProvider(35.0, 240.0),
        )
        dataset = make_dataset()

        first = calculator.calculate(dataset, self.departure)
        second = calculator.calculate(dataset, self.departure)

        self.assertEqual(first, second)
        self.assertEqual(first.geometry.wkb, second.geometry.wkb)


if __name__ == "__main__":
    unittest.main()
