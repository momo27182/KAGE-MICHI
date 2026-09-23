import unittest

import geopandas as gpd
from shapely.geometry import Point, Polygon

from kage_michi.infrastructure.facilities import prepare_facility_markers


class FacilityMarkerTests(unittest.TestCase):
    def test_classifies_optional_columns_and_uses_representative_points(self):
        spots = gpd.GeoDataFrame(
            {
                "name:ja": ["駅前店", None, None],
                "name": ["Station Store", None, None],
                "shop": ["convenience", None, "convenience"],
                "amenity": [None, "drinking_water", None],
            },
            geometry=[
                Point(-304800, -191100),
                Point(-304700, -191000),
                Polygon([
                    (-304600, -190900), (-304580, -190900),
                    (-304580, -190880), (-304600, -190880),
                ]),
            ],
            crs="EPSG:6676",
        )

        markers = prepare_facility_markers(spots)

        self.assertEqual([marker.kind for marker in markers], [
            "convenience", "drinking_water", "convenience"
        ])
        self.assertEqual([marker.name for marker in markers], [
            "駅前店", "名称未登録", "名称未登録"
        ])
        self.assertTrue(all(33 < marker.latitude < 35 for marker in markers))
        self.assertTrue(all(134 < marker.longitude < 136 for marker in markers))

    def test_empty_and_missing_classification_columns_are_valid(self):
        empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:6676")
        unclassified = gpd.GeoDataFrame(
            {"name": [None]}, geometry=[Point(-304800, -191100)], crs="EPSG:6676"
        )

        self.assertEqual(prepare_facility_markers(empty), ())
        self.assertEqual(prepare_facility_markers(unclassified), ())

    def test_many_facilities_are_not_silently_truncated(self):
        count = 500
        spots = gpd.GeoDataFrame(
            {"shop": ["convenience"] * count},
            geometry=[Point(-304800 + index, -191100) for index in range(count)],
            crs="EPSG:6676",
        )

        self.assertEqual(len(prepare_facility_markers(spots)), count)


if __name__ == "__main__":
    unittest.main()
