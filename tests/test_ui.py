from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.data import SpatialDataset
from kage_michi.models import GeoPoint, RouteResult
from kage_michi.shadows import ShadowResult
from kage_michi.ui import (
    UiInputs,
    build_disclosure,
    changed_stages,
    recalculation_keys,
)


class UiStateTests(unittest.TestCase):
    departure = datetime(2026, 8, 11, 14, tzinfo=timezone(timedelta(hours=9)))

    def inputs(self, **changes) -> UiInputs:
        values = {
            "data_directory": "prepared/wakayama",
            "start": GeoPoint(34.2325, 135.1917),
            "destination": GeoPoint(34.2241, 135.1906),
            "departure": self.departure,
            "sun_penalty": 10.0,
        }
        values.update(changes)
        return UiInputs(**values)

    def test_point_change_recalculates_route_only(self) -> None:
        before = recalculation_keys(self.inputs(), "v1")
        after = recalculation_keys(
            self.inputs(destination=GeoPoint(34.225, 135.191)), "v1"
        )
        self.assertEqual(changed_stages(before, after), ("route",))

    def test_datetime_change_recalculates_shadows_and_route(self) -> None:
        before = recalculation_keys(self.inputs(), "v1")
        after = recalculation_keys(
            self.inputs(departure=self.departure + timedelta(hours=1)), "v1"
        )
        self.assertEqual(changed_stages(before, after), ("shadows", "route"))

    def test_data_change_recalculates_every_stage(self) -> None:
        before = recalculation_keys(self.inputs(), "v1")
        after = recalculation_keys(self.inputs(), "v2")
        self.assertEqual(
            changed_stages(before, after), ("dataset", "shadows", "route")
        )

    def test_disclosure_includes_time_source_and_limitations(self) -> None:
        dataset = SpatialDataset(
            object(), "OpenStreetMap", "2026-08-10T00:00:00Z", "radius=1700m", "EPSG:6676"
        )
        calculated = datetime(2026, 8, 11, 5, tzinfo=timezone.utc)
        disclosure = build_disclosure(
            dataset,
            ShadowResult(None, 45, 180),
            RouteResult((1, 2), 1000, 250),
            self.departure,
            calculated,
        )
        self.assertEqual(disclosure.data_source, "OpenStreetMap")
        self.assertEqual(disclosure.data_acquired_at, "2026-08-10T00:00:00Z")
        self.assertEqual(disclosure.calculated_at_iso, calculated.isoformat())
        self.assertEqual(disclosure.shade_ratio_pct, 75)
        self.assertTrue(any("推定値" in warning for warning in disclosure.warnings))
        self.assertTrue(any("中央点" in warning for warning in disclosure.warnings))


if __name__ == "__main__":
    unittest.main()
