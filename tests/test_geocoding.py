from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from geopy.exc import GeocoderTimedOut, GeocoderUnavailable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.geocoding import (
    GeocodingResult,
    PlaceSearchTimedOut,
    PlaceSearchUnavailable,
    SearchArea,
    search_places,
)
from kage_michi.infrastructure.nominatim_geocoder import NominatimPlaceGeocoder
from kage_michi.infrastructure.ui_runtime import search_places_cached
from kage_michi.models import GeoPoint


AREA = SearchArea(GeoPoint(34.2325, 135.1917), 1_700)


class FakeGeocoder:
    def __init__(self, results=(), error=None) -> None:
        self.results = tuple(results)
        self.error = error
        self.queries = []

    def geocode(self, query, area):
        self.queries.append((query, area))
        if self.error:
            raise self.error
        return self.results


class FakeLocation:
    def __init__(self, address, latitude, longitude, raw) -> None:
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.raw = raw


class PlaceSearchTests(unittest.TestCase):
    def result(self, name, latitude, longitude, provider_id, address=None):
        return GeocodingResult(
            name,
            address or f"{name}, 和歌山市, 和歌山県, 日本",
            GeoPoint(latitude, longitude),
            provider_id,
        )

    def test_representative_place_address_and_facility_queries(self) -> None:
        cases = {
            "和歌山市": (
                self.result("和歌山市", 34.2343, 135.1784, "relation:1"),
                "results",
            ),
            "和歌山市美園町5丁目": (
                self.result("美園町5丁目", 34.2314, 135.1908, "way:2"),
                "results",
            ),
            "和歌山駅": (
                self.result("和歌山駅", 34.2322, 135.1918, "node:3"),
                "results",
            ),
        }
        for query, (result, expected_status) in cases.items():
            with self.subTest(query=query):
                geocoder = FakeGeocoder((result,))
                outcome = search_places(query, geocoder, AREA)
                self.assertEqual(outcome.status, expected_status)
                self.assertEqual(outcome.candidates[0].name, result.name)
                self.assertEqual(
                    outcome.candidates[0].in_scope, expected_status == "results"
                )

    def test_candidates_are_deduplicated_and_ranked_in_scope_first(self) -> None:
        results = (
            self.result("遠い候補", 34.40, 135.20, "node:far"),
            self.result("和歌山駅", 34.2322, 135.1918, "node:station", "和歌山駅"),
            self.result(
                "和歌山駅",
                34.2322,
                135.1918,
                "node:duplicate",
                "和歌山駅, 美園町, 和歌山市, 和歌山県, 日本",
            ),
            self.result("近い候補", 34.2330, 135.1920, "node:near"),
        )
        outcome = search_places("和歌山", FakeGeocoder(results), AREA)

        self.assertEqual(outcome.status, "ambiguous")
        self.assertEqual([item.name for item in outcome.candidates], ["和歌山駅", "近い候補", "遠い候補"])
        self.assertTrue(outcome.candidates[0].in_scope)
        self.assertFalse(outcome.candidates[-1].in_scope)
        self.assertIn("中心から", outcome.candidates[0].display_label)

    def test_no_results_and_out_of_scope_are_distinct(self) -> None:
        empty = search_places("存在しない場所", FakeGeocoder(), AREA)
        outside = search_places(
            "大阪駅",
            FakeGeocoder((self.result("大阪駅", 34.7025, 135.4959, "node:osaka"),)),
            AREA,
        )

        self.assertEqual(empty.status, "no_results")
        self.assertEqual(outside.status, "out_of_scope")
        self.assertFalse(outside.candidates[0].in_scope)

    def test_provider_failures_become_user_visible_states(self) -> None:
        timeout = search_places(
            "和歌山駅", FakeGeocoder(error=PlaceSearchTimedOut()), AREA
        )
        unavailable = search_places(
            "和歌山駅", FakeGeocoder(error=PlaceSearchUnavailable()), AREA
        )

        self.assertEqual(timeout.status, "timeout")
        self.assertEqual(unavailable.status, "unavailable")
        self.assertIn("緯度経度", unavailable.message)


class NominatimPlaceGeocoderTests(unittest.TestCase):
    def test_adapter_uses_one_biased_non_autocomplete_request(self) -> None:
        calls = []

        def fake_geocode(query, **kwargs):
            calls.append((query, kwargs))
            return [
                FakeLocation(
                    "和歌山駅, 美園町, 和歌山市, 和歌山県, 日本",
                    34.2322,
                    135.1918,
                    {
                        "osm_type": "node",
                        "osm_id": 123,
                        "type": "station",
                        "namedetails": {"name:ja": "和歌山駅"},
                    },
                )
            ]

        adapter = NominatimPlaceGeocoder(
            user_agent="KAGE-MICHI-tests", geocode_function=fake_geocode
        )
        results = adapter.geocode("和歌山駅", AREA)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "Wakayama Station, Wakayama, Japan")
        self.assertEqual(calls[0][1]["country_codes"], "jp")
        self.assertFalse(calls[0][1]["bounded"])
        self.assertEqual(results[0].name, "和歌山駅")
        self.assertEqual(results[0].provider_id, "node:123")

    def test_adapter_maps_timeout_and_unavailable(self) -> None:
        for provider_error, expected in (
            (GeocoderTimedOut("late"), PlaceSearchTimedOut),
            (GeocoderUnavailable("down"), PlaceSearchUnavailable),
        ):
            with self.subTest(provider_error=type(provider_error).__name__):
                def fail(*args, **kwargs):
                    raise provider_error

                adapter = NominatimPlaceGeocoder(
                    user_agent="KAGE-MICHI-tests", geocode_function=fail
                )
                with self.assertRaises(expected):
                    adapter.geocode("和歌山駅", AREA)


class CachedPlaceSearchTests(unittest.TestCase):
    def test_identical_search_uses_streamlit_cache(self) -> None:
        geocoder = FakeGeocoder(
            (
                GeocodingResult(
                    "和歌山駅",
                    "和歌山駅, 和歌山市, 和歌山県, 日本",
                    GeoPoint(34.2322, 135.1918),
                    "node:station",
                ),
            )
        )
        manifest = {
            "schema_version": 1,
            "source": "OpenStreetMap via OSMnx",
            "attribution": "© OpenStreetMap contributors",
            "copyright_url": "https://www.openstreetmap.org/copyright",
            "acquired_at_utc": "2026-08-10T00:00:00+00:00",
            "source_timestamp_note": "test",
            "center": {"latitude": 34.2325, "longitude": 135.1917},
            "radius_m": 1700,
            "crs": "EPSG:6676",
            "default_building_height_m": 10.0,
            "files": {},
            "sha256": {},
            "counts": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            search_places_cached.clear()
            with patch(
                "kage_michi.infrastructure.ui_runtime.get_place_geocoder",
                return_value=geocoder,
            ):
                first = search_places_cached(
                    "和歌山駅", directory, "v1", "example.test", "test-agent"
                )
                second = search_places_cached(
                    "和歌山駅", directory, "v1", "example.test", "test-agent"
                )

        self.assertEqual(first, second)
        self.assertEqual(len(geocoder.queries), 1)


if __name__ == "__main__":
    unittest.main()
