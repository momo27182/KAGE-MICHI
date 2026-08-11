from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import unittest
from unittest.mock import patch

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.osm_prepared import (
    MANIFEST_FILE,
    OsmPreparationConfig,
    OsmSpatialPayload,
    PreparedOsmDataSource,
    _make_manifest,
    load_prepared_dataset,
    save_prepared_dataset,
)
from kage_michi.models import GeoPoint


class PreparedOsmDataTests(unittest.TestCase):
    def make_payload(self) -> OsmSpatialPayload:
        config = OsmPreparationConfig(GeoPoint(34.2325, 135.1917), radius_m=1_700)
        graph = nx.MultiDiGraph(crs="EPSG:6676")
        graph.add_node(1, x=0.0, y=0.0)
        graph.add_node(2, x=10.0, y=0.0)
        graph.add_edge(1, 2, length=10.0)
        buildings = gpd.GeoDataFrame(
            {"height": [10.0]}, geometry=[Point(0, 0)], crs="EPSG:6676"
        )
        spots = gpd.GeoDataFrame(
            {"kind": ["water"]}, geometry=[Point(1, 1)], crs="EPSG:6676"
        )
        manifest = _make_manifest(
            config,
            datetime(2026, 8, 10, tzinfo=timezone.utc).isoformat(),
            graph,
            buildings,
            spots,
        )
        return OsmSpatialPayload(graph, buildings, spots, manifest)

    def test_save_and_offline_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            with patch(
                "kage_michi.infrastructure.osm_prepared.fetch_osm_data",
                side_effect=AssertionError("offline loader must not fetch OSM"),
            ):
                started = perf_counter()
                dataset = PreparedOsmDataSource(Path(directory)).load(
                    GeoPoint(34.2325, 135.1917),
                    GeoPoint(34.2241, 135.1906),
                )
                elapsed = perf_counter() - started

        payload = dataset.payload
        self.assertEqual(payload.graph.number_of_nodes(), 2)
        self.assertEqual(payload.graph.number_of_edges(), 1)
        self.assertEqual(len(payload.buildings), 1)
        self.assertEqual(len(payload.spots), 1)
        self.assertEqual(dataset.source, "OpenStreetMap via OSMnx")
        self.assertEqual(dataset.crs, "EPSG:6676")
        self.assertLess(elapsed, 3.0)

    def test_manifest_records_traceability_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            manifest = json.loads(
                (Path(directory) / MANIFEST_FILE).read_text(encoding="utf-8")
            )

        self.assertEqual(manifest["attribution"], "© OpenStreetMap contributors")
        self.assertEqual(manifest["radius_m"], 1_700)
        self.assertEqual(manifest["crs"], "EPSG:6676")
        self.assertIn("acquired_at_utc", manifest)
        self.assertIn("OSMnx HTTP cache", manifest["source_timestamp_note"])
        self.assertEqual(set(manifest["sha256"]), {"graph", "buildings", "spots"})
        self.assertEqual(manifest["counts"]["road_nodes"], 2)

    def test_save_refuses_to_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            with self.assertRaises(FileExistsError):
                save_prepared_dataset(self.make_payload(), directory)

    def test_missing_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            os.remove(Path(directory) / "spots.gpkg")
            with self.assertRaisesRegex(FileNotFoundError, "spots.gpkg"):
                load_prepared_dataset(directory)

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            with (Path(directory) / "walk.graphml").open("ab") as graph_file:
                graph_file.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch: graph"):
                load_prepared_dataset(directory)

    def test_points_outside_prepared_scope_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_prepared_dataset(self.make_payload(), directory)
            source = PreparedOsmDataSource(Path(directory))
            with self.assertRaisesRegex(ValueError, "destination"):
                source.load(
                    GeoPoint(34.2325, 135.1917),
                    GeoPoint(35.0, 135.1917),
                )


if __name__ == "__main__":
    unittest.main()
