from pathlib import Path
from datetime import date
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import folium

from streamlit.testing.v1 import AppTest

from kage_michi.geocoding import SearchArea
from kage_michi.models import GeoPoint
from kage_michi.infrastructure import map_picker
from kage_michi.infrastructure.facilities import FacilityMarker


ROOT = Path(__file__).resolve().parents[1]
AREA = SearchArea(GeoPoint(34.2325, 135.1917), 1700)


class MapSelectionTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(start_latitude=34.2325, start_longitude=135.1917,
                          destination_latitude=34.2241, destination_longitude=135.1906,
                          map_role="start")
        self.stub = patch.object(map_picker, "st", SimpleNamespace(session_state=self.state))
        self.stub.start()
        self.addCleanup(self.stub.stop)

    def click(self, lat, lng):
        self.state["event"] = {"last_clicked": {"lat": lat, "lng": lng},
                               "center": {"lat": 34.23, "lng": 135.19}, "zoom": 16}
        map_picker.receive_event("event", AREA)

    def test_latest_click_wins_without_confirming(self):
        self.click(34.23, 135.19)
        self.click(34.231, 135.192)
        self.assertEqual(self.state["map_pending"], GeoPoint(34.231, 135.192))
        self.assertEqual(self.state["start_latitude"], 34.2325)
        map_picker.confirm_candidate(AREA)
        self.assertEqual(self.state["start_latitude"], 34.231)
        self.assertNotIn("map_pending", self.state)
        self.assertEqual(self.state["map_zoom"], 16)

    def test_outside_and_same_point_clear_old_candidate(self):
        for point in [(35, 135), (34.2241, 135.1906), (float("nan"), 135)]:
            self.click(34.23, 135.19)
            self.click(*point)
            self.assertNotIn("map_pending", self.state)
            self.assertIn("map_error", self.state)

    def test_cancel_then_reselect_same_coordinate(self):
        self.click(34.23, 135.19)
        map_picker.clear_candidate()
        self.assertNotIn("map_pending", self.state)
        self.click(34.23, 135.19)
        self.assertIn("map_pending", self.state)

    def test_pan_does_not_replay_click(self):
        self.click(34.23, 135.19)
        self.state.pop("map_pending")
        self.state["event"]["zoom"] = 17
        map_picker.receive_event("event", AREA)
        self.assertNotIn("map_pending", self.state)
        self.assertEqual(self.state["map_zoom"], 17)

    def test_confirm_revalidates_after_other_endpoint_changes(self):
        self.click(34.23, 135.19)
        self.state["destination_latitude"] = 34.23
        self.state["destination_longitude"] = 135.19
        map_picker.confirm_candidate(AREA)
        self.assertEqual(self.state["start_latitude"], 34.2325)
        self.assertIn("map_error", self.state)


class MapScreenTests(unittest.TestCase):
    def test_confirm_cancel_and_role_switch_do_not_compute(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("kage_michi.infrastructure.osm_prepared.PreparedDatasetManifest.from_json",
                   return_value=SimpleNamespace(
                       center={"latitude": 34.2325, "longitude": 135.1917},
                       radius_m=1700,
                       attribution="© OpenStreetMap contributors",
                       acquired_at_utc="2026-08-10T13:26:00+00:00",
                   )), \
             patch("kage_michi.infrastructure.ui_runtime.load_dataset_cached") as load, \
             patch("kage_michi.infrastructure.ui_runtime.calculate_shadows_cached") as shadows, \
             patch("kage_michi.infrastructure.ui_runtime.calculate_route_comparison_cached") as route, \
             patch("kage_michi.infrastructure.ui_runtime.load_facilities_cached",
                   return_value=(
                       FacilityMarker("convenience", "店舗", 34.231, 135.192),
                       FacilityMarker("drinking_water", "給水", 34.230, 135.191),
                   )) as facilities, \
             patch("kage_michi.infrastructure.map_picker.st_folium") as map_view:
            Path(directory, "manifest.json").write_text("{}", encoding="utf-8")
            app = AppTest.from_file(str(ROOT / "src/streamlit_app.py")).run(timeout=30)
            app.text_input[0].set_value(directory).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("コンビニ 1件 / 給水地点 1件" in item.value
                                for item in app.caption))
            initial_key = map_view.call_args.kwargs["key"]
            initial_center = map_view.call_args.kwargs["center"]
            app.session_state["map_center"] = {"lat": 34.231, "lng": 135.194}
            app.session_state["map_zoom"] = 16
            app.run()
            self.assertEqual(map_view.call_args.kwargs["center"], initial_center)
            self.assertEqual(map_view.call_args.kwargs["zoom"], 15)
            app.session_state["map_pending"] = GeoPoint(34.23, 135.19)
            app.run()
            features = map_view.call_args.kwargs["feature_group_to_add"]
            markers = [child.location for child in features._children.values()
                       if type(child) is folium.Marker]
            self.assertIn([34.23, 135.19], markers)
            app.button(key="map_confirm").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(map_view.call_args.kwargs["key"], initial_key)
            self.assertEqual(map_view.call_args.kwargs["center"], initial_center)
            self.assertEqual(map_view.call_args.kwargs["zoom"], 15)
            self.assertEqual(app.number_input(key="start_latitude").value, 34.23)
            features = map_view.call_args.kwargs["feature_group_to_add"]
            markers = [child.location for child in features._children.values()
                       if type(child) is folium.Marker]
            self.assertEqual(markers, [[34.23, 135.19], [34.2241, 135.1906]])
            marker_classes = [next(iter(child._children.values())).options["class_name"]
                              for child in features._children.values()
                              if type(child) is folium.Marker]
            self.assertEqual(marker_classes, ["endpoint-marker endpoint-start",
                                               "endpoint-marker endpoint-destination"])
            facility_markers = [child for child in features._children.values()
                                if type(child) is folium.CircleMarker]
            self.assertEqual(len(facility_markers), 2)
            app.checkbox[1].uncheck().run()
            filtered_features = map_view.call_args.kwargs["feature_group_to_add"]
            self.assertEqual(
                len([child for child in filtered_features._children.values()
                     if type(child) is folium.CircleMarker]),
                1,
            )
            app.radio(key="map_role").set_value("destination").run()
            app.session_state["map_pending"] = GeoPoint(34.225, 135.19)
            app.run()
            app.button(key="map_cancel").click().run()
            self.assertTrue(app.button(key="map_confirm").disabled)
            app.session_state["map_pending"] = GeoPoint(34.225, 135.19)
            app.text_input[0].set_value(str(Path(directory) / "missing")).run()
            self.assertNotIn("map_pending", app.session_state)
            app.text_input[0].set_value(directory).run()
            self.assertTrue(app.button(key="map_confirm").disabled)
            self.assertFalse(app.exception)
            load.assert_not_called()
            facilities.assert_called()
            shadows.assert_not_called()
            route.assert_not_called()

    @unittest.skipUnless((ROOT / "data/prepared/wakayama-station/manifest.json").exists(),
                         "Representative integration requires prepared Wakayama dataset")
    def test_result_survives_rerun_and_hides_after_input_change(self):
        with patch("kage_michi.infrastructure.map_picker.st_folium") as map_view:
            app = AppTest.from_file(str(ROOT / "src/streamlit_app.py")).run(timeout=30)
            app.date_input[0].set_value(date(2026, 8, 11)).run()
            app.date_input[1].set_value(date(2026, 8, 11)).run()
            next(b for b in app.button if b.label == "2時刻を比較").click().run(timeout=60)
            self.assertFalse(app.exception)
            self.assertTrue(any(m.label == "距離増加" for m in app.metric))
            self.assertTrue(any("基準・最短" in item.value and "比較・日陰優先" in item.value
                                for item in app.markdown))
            self.assertTrue(any("地図凡例" in item.value for item in app.caption))
            features = map_view.call_args.kwargs["feature_group_to_add"]
            routes = [child for child in features._children.values()
                      if type(child) is folium.PolyLine]
            self.assertEqual(
                [route.options["color"] for route in routes],
                ["#167d4a", "#d32f2f", "#1565c0", "#ef6c00"],
            )
            with patch("kage_michi.infrastructure.ui_runtime.calculate_shadows_cached") as shadows, \
                 patch("kage_michi.infrastructure.ui_runtime.calculate_route_comparison_cached") as route:
                app.run()
                self.assertTrue(any(m.label == "距離増加" for m in app.metric))
                app.number_input(key="start_latitude").set_value(34.231).run()
                self.assertFalse(app.exception)
                self.assertFalse(app.metric)
                self.assertTrue(any("前回の経路を非表示" in w.value for w in app.warning))
                shadows.assert_not_called()
                route.assert_not_called()

    @unittest.skipUnless((ROOT / "data/prepared/wakayama-station/manifest.json").exists(),
                         "Representative integration requires prepared Wakayama dataset")
    def test_same_time_and_missing_comparison_date_are_explicit(self):
        app = AppTest.from_file(str(ROOT / "src/streamlit_app.py")).run(timeout=30)
        app.date_input[0].set_value(date(2026, 8, 11)).run()
        app.date_input[1].set_value(date(2026, 8, 11)).run()
        app.time_input[1].set_value(app.time_input[0].value).run()
        next(b for b in app.button if b.label == "2時刻を比較").click().run(timeout=60)
        self.assertTrue(any("異なる日時" in item.value for item in app.error))

        app.date_input[1].set_value(date(2026, 8, 12)).run()
        next(b for b in app.button if b.label == "2時刻を比較").click().run(timeout=60)
        self.assertTrue(
            any("対象日時=2026-08-12" in item.value for item in app.error)
        )
