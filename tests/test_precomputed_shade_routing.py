from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

import networkx as nx
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.data import SpatialDataset
from kage_michi.infrastructure.precomputed_shade import (
    NIGHTTIME_SEMANTICS,
    SHADE_MODEL_VERSION,
    PreparedShadeRatios,
    ShadeArtifactManifest,
)
from kage_michi.infrastructure.precomputed_shade_routing import (
    PrecomputedShadeRoutePlanner,
    ShadeTimeUnavailableError,
    resolve_shade_time,
)
from kage_michi.models import GeoPoint


JST = ZoneInfo("Asia/Tokyo")


def make_dataset(*, extra_edge: bool = False) -> SpatialDataset:
    graph = nx.MultiDiGraph(crs="EPSG:3857")
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=10.0, y=10.0)
    graph.add_node(3, x=20.0, y=0.0)
    graph.add_edge(1, 2, key=0, length=14.0)
    graph.add_edge(1, 3, key=0, length=20.0)
    graph.add_edge(2, 3, key=0, length=14.0)
    if extra_edge:
        graph.add_edge(3, 1, key=0, length=20.0)
    manifest = SimpleNamespace(sha256={"graph": "roads"})
    return SpatialDataset(
        SimpleNamespace(graph=graph, manifest=manifest),
        "test roads",
        "fixed",
        "unit",
        "EPSG:3857",
    )


def make_prepared(*, daylight: bool = True) -> PreparedShadeRatios:
    timestamps = (
        "2026-08-11T14:00:00+09:00",
        "2026-08-11T14:05:00+09:00",
    )
    manifest = ShadeArtifactManifest(
        schema_version=1,
        shade_model_version=SHADE_MODEL_VERSION,
        prepared_at_utc="2026-09-24T00:00:00+00:00",
        region="test",
        start=timestamps[0],
        end=timestamps[-1],
        timezone="Asia/Tokyo",
        interval_minutes=5,
        sample_spacing_m=5.0,
        projected_crs="EPSG:3857",
        source_sha256={"osm_graph": "roads", "plateau_buildings": "buildings"},
        files={"ratios": "shade-ratios.npz"},
        output_sha256={"ratios": "unused"},
        semantic_sha256="unused",
        counts={"timestamps": 2, "daylight_timestamps": 2, "edges": 3},
        nighttime_semantics=NIGHTTIME_SEMANTICS,
        metrics={},
    )
    return PreparedShadeRatios(
        manifest=manifest,
        timestamps=timestamps,
        daylight=np.asarray([daylight, daylight], dtype=np.bool_),
        solar_altitude_deg=np.asarray([45.0, 44.0], dtype=np.float32),
        edge_u=("1", "1", "2"),
        edge_v=("2", "3", "3"),
        edge_key=("0", "0", "0"),
        ratios=np.asarray([[1.0, 0.0, 1.0], [0.5, 0.5, 0.5]], dtype=np.float32),
    )


class PrecomputedShadeRoutingTests(unittest.TestCase):
    start = GeoPoint(0.0, 0.0)
    destination = GeoPoint(0.0, 0.00018)

    def test_resolves_to_previous_five_minute_slot(self) -> None:
        resolved = resolve_shade_time(
            make_prepared(), datetime(2026, 8, 11, 14, 4, 59, tzinfo=JST)
        )

        self.assertEqual(resolved.index, 0)
        self.assertEqual(resolved.resolved.isoformat(), "2026-08-11T14:00:00+09:00")
        self.assertTrue(resolved.daylight)

    def test_missing_time_is_explicit(self) -> None:
        with self.assertRaisesRegex(ShadeTimeUnavailableError, "ありません"):
            resolve_shade_time(
                make_prepared(), datetime(2026, 8, 12, 14, 0, tzinfo=JST)
            )

    def test_routes_from_precomputed_partial_ratios(self) -> None:
        planner = PrecomputedShadeRoutePlanner(sun_penalty=10)
        comparison, resolved = planner.compare_routes(
            make_dataset(),
            self.start,
            self.destination,
            make_prepared(),
            datetime(2026, 8, 11, 14, 4, tzinfo=JST),
        )

        self.assertEqual(comparison.shortest.node_ids, (1, 3))
        self.assertEqual(comparison.shortest.sunny_distance_m, 20.0)
        self.assertEqual(comparison.shade_optimized.node_ids, (1, 2, 3))
        self.assertEqual(comparison.shade_optimized.sunny_distance_m, 0.0)
        self.assertEqual(resolved.index, 0)

    def test_edge_key_mismatch_is_not_ignored(self) -> None:
        with self.assertRaisesRegex(ValueError, "edge keys do not match"):
            PrecomputedShadeRoutePlanner().compare_routes(
                make_dataset(extra_edge=True),
                self.start,
                self.destination,
                make_prepared(),
                datetime(2026, 8, 11, 14, 0, tzinfo=JST),
            )

    def test_nighttime_state_is_preserved(self) -> None:
        resolved = resolve_shade_time(
            make_prepared(daylight=False),
            datetime(2026, 8, 11, 14, 0, tzinfo=JST),
        )
        self.assertFalse(resolved.daylight)


if __name__ == "__main__":
    unittest.main()
