from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest

import networkx as nx
import numpy as np
from shapely.geometry import LineString, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.precomputed_shade import (
    DATA_FILE,
    NIGHTTIME_SEMANTICS,
    MANIFEST_FILE,
    ShadeTimeRange,
    generate_shade_artifact,
    load_shade_artifact,
)
from kage_michi.shadows import ShadowResult


JST = timezone(timedelta(hours=9))


def make_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:6676")
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=20.0, y=0.0)
    graph.add_node(3, x=40.0, y=0.0)
    graph.add_edge(2, 3, key=0, length=20.0)
    graph.add_edge(
        1,
        2,
        key=5,
        length=20.0,
        geometry=LineString([(0, 0), (20, 0)]),
    )
    return graph


def daytime_shadow(_: datetime) -> ShadowResult:
    return ShadowResult(
        geometry=Polygon([(0, -1), (10, -1), (10, 1), (0, 1)]),
        solar_altitude_deg=45.0,
        solar_azimuth_deg=180.0,
    )


class PrecomputedShadeTests(unittest.TestCase):
    def test_round_trip_uses_stable_edges_and_partial_ratios(self) -> None:
        start = datetime(2026, 8, 11, 12, 0, tzinfo=JST)
        config = ShadeTimeRange(start, start + timedelta(minutes=5))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "shade"
            generate_shade_artifact(
                make_graph(),
                daytime_shadow,
                destination,
                config,
                {"roads": "abc"},
                region="test-area",
            )

            loaded = load_shade_artifact(
                destination, expected_source_sha256={"roads": "abc"}
            )

        self.assertEqual(loaded.edge_u, ("1", "2"))
        self.assertEqual(loaded.edge_v, ("2", "3"))
        self.assertEqual(loaded.edge_key, ("5", "0"))
        np.testing.assert_array_equal(loaded.ratios[:, 0], [0.5, 0.5])
        np.testing.assert_array_equal(loaded.ratios[:, 1], [0.0, 0.0])
        np.testing.assert_array_equal(loaded.ratios_at(start), [0.5, 0.0])
        self.assertEqual(loaded.manifest.counts["samples"], 8)
        self.assertEqual(loaded.manifest.region, "test-area")
        self.assertGreaterEqual(loaded.manifest.metrics["validation_load_seconds"], 0)

    def test_nighttime_is_zero_direct_exposure_not_building_claim(self) -> None:
        start = datetime(2026, 8, 11, 0, 0, tzinfo=JST)

        def nighttime(_: datetime) -> ShadowResult:
            return ShadowResult(None, -20.0, 0.0)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "shade"
            generate_shade_artifact(
                make_graph(),
                nighttime,
                destination,
                ShadeTimeRange(start, start),
                {"roads": "abc"},
                region="test-area",
            )
            loaded = load_shade_artifact(destination)

        self.assertFalse(loaded.daylight[0])
        np.testing.assert_array_equal(loaded.ratios[0], [1.0, 1.0])
        self.assertEqual(loaded.manifest.nighttime_semantics, NIGHTTIME_SEMANTICS)

    def test_refuses_overwrite_and_detects_tampering_and_source_change(self) -> None:
        start = datetime(2026, 8, 11, 12, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "shade"
            generate_shade_artifact(
                make_graph(),
                daytime_shadow,
                destination,
                ShadeTimeRange(start, start),
                {"roads": "abc"},
                region="test-area",
            )
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                generate_shade_artifact(
                    make_graph(),
                    daytime_shadow,
                    destination,
                    ShadeTimeRange(start, start),
                    {"roads": "abc"},
                    region="test-area",
                )
            with self.assertRaisesRegex(ValueError, "source version"):
                load_shade_artifact(destination, expected_source_sha256={"roads": "changed"})
            manifest_path = destination / MANIFEST_FILE
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["shade_model_version"] = "obsolete-v0"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "model version"):
                load_shade_artifact(destination)
            manifest["shade_model_version"] = "convex-hull-v1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with (destination / DATA_FILE).open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_shade_artifact(destination)

    def test_failed_generation_leaves_no_published_or_temporary_artifact(self) -> None:
        start = datetime(2026, 8, 11, 12, 0, tzinfo=JST)

        def fail(_: datetime) -> ShadowResult:
            raise RuntimeError("failed")

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "shade"
            with self.assertRaisesRegex(RuntimeError, "failed"):
                generate_shade_artifact(
                    make_graph(),
                    fail,
                    destination,
                    ShadeTimeRange(start, start),
                    {"roads": "abc"},
                    region="test-area",
                )
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_time_range_requires_timezone_and_positive_interval(self) -> None:
        aware = datetime(2026, 8, 11, tzinfo=JST)
        with self.assertRaisesRegex(ValueError, "timezone"):
            ShadeTimeRange(aware.replace(tzinfo=None), aware)
        with self.assertRaisesRegex(ValueError, "positive"):
            ShadeTimeRange(aware, aware, interval_minutes=0)
        end = aware + timedelta(days=1) - timedelta(minutes=5)
        self.assertEqual(len(ShadeTimeRange(aware, end).timestamps()), 288)


if __name__ == "__main__":
    unittest.main()
