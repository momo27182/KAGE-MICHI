"""Fetch OSM once, persist projected artifacts, and load them offline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd

from ..data import SpatialDataset
from ..models import GeoPoint


SCHEMA_VERSION = 1
GRAPH_FILE = "walk.graphml"
BUILDINGS_FILE = "buildings.gpkg"
SPOTS_FILE = "spots.gpkg"
MANIFEST_FILE = "manifest.json"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"


@dataclass(frozen=True)
class OsmPreparationConfig:
    center: GeoPoint
    radius_m: int = 1_700
    projected_crs: str = "EPSG:6676"
    default_building_height_m: float = 10.0

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.default_building_height_m <= 0:
            raise ValueError("default_building_height_m must be positive")
        if not self.projected_crs.strip():
            raise ValueError("projected_crs must not be empty")


@dataclass(frozen=True)
class PreparedDatasetManifest:
    schema_version: int
    source: str
    attribution: str
    copyright_url: str
    acquired_at_utc: str
    source_timestamp_note: str
    center: dict[str, float]
    radius_m: int
    crs: str
    default_building_height_m: float
    files: dict[str, str]
    sha256: dict[str, str]
    counts: dict[str, int]

    @classmethod
    def from_json(cls, path: Path) -> "PreparedDatasetManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest = cls(**raw)
        if manifest.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported prepared dataset schema: {manifest.schema_version}"
            )
        return manifest


@dataclass
class OsmSpatialPayload:
    graph: nx.MultiDiGraph
    buildings: gpd.GeoDataFrame
    spots: gpd.GeoDataFrame
    manifest: PreparedDatasetManifest


def fetch_osm_data(config: OsmPreparationConfig) -> OsmSpatialPayload:
    """Download and project OSM data. This is the only network-facing function."""
    point = (config.center.latitude, config.center.longitude)
    graph = ox.graph_from_point(point, dist=config.radius_m, network_type="walk")
    graph = ox.truncate.largest_component(graph, strongly=True)
    buildings = ox.features_from_point(
        point, tags={"building": True}, dist=config.radius_m
    ).copy()
    spots = ox.features_from_point(
        point,
        tags={"shop": "convenience", "amenity": "drinking_water"},
        dist=config.radius_m,
    ).copy()

    if "height" not in buildings.columns:
        buildings["height"] = config.default_building_height_m
    else:
        buildings["height"] = pd.to_numeric(
            buildings["height"], errors="coerce"
        ).fillna(config.default_building_height_m)

    projected_graph = ox.project_graph(graph, to_crs=config.projected_crs)
    projected_buildings = buildings.to_crs(config.projected_crs)
    projected_spots = spots.to_crs(config.projected_crs)
    acquired_at = datetime.now(timezone.utc).isoformat()
    manifest = _make_manifest(
        config,
        acquired_at,
        projected_graph,
        projected_buildings,
        projected_spots,
    )
    return OsmSpatialPayload(
        graph=projected_graph,
        buildings=projected_buildings,
        spots=projected_spots,
        manifest=manifest,
    )


def save_prepared_dataset(
    payload: OsmSpatialPayload,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist one complete prepared dataset, writing the manifest last."""
    directory = Path(destination)
    targets = [
        directory / GRAPH_FILE,
        directory / BUILDINGS_FILE,
        directory / SPOTS_FILE,
        directory / MANIFEST_FILE,
    ]
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"prepared dataset already exists: {names}")

    directory.mkdir(parents=True, exist_ok=True)
    ox.io.save_graphml(payload.graph, directory / GRAPH_FILE)
    payload.buildings.to_file(directory / BUILDINGS_FILE, driver="GPKG", index=False)
    payload.spots.to_file(directory / SPOTS_FILE, driver="GPKG", index=False)
    manifest = replace(
        payload.manifest,
        sha256={
            "graph": _sha256(directory / GRAPH_FILE),
            "buildings": _sha256(directory / BUILDINGS_FILE),
            "spots": _sha256(directory / SPOTS_FILE),
        },
    )
    (directory / MANIFEST_FILE).write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return directory


def load_prepared_dataset(directory: str | Path) -> SpatialDataset:
    """Load prepared files only; this function never calls an OSM endpoint."""
    root = Path(directory)
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prepared manifest not found: {manifest_path}")
    manifest = PreparedDatasetManifest.from_json(manifest_path)
    paths = {name: root / filename for name, filename in manifest.files.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"prepared dataset files missing: {', '.join(missing)}")
    invalid = [
        name
        for name, path in paths.items()
        if manifest.sha256.get(name) != _sha256(path)
    ]
    if invalid:
        raise ValueError(f"prepared dataset checksum mismatch: {', '.join(invalid)}")

    graph = ox.io.load_graphml(paths["graph"])
    buildings = gpd.read_file(paths["buildings"])
    spots = gpd.read_file(paths["spots"])
    _validate_loaded_crs(graph, buildings, spots, manifest.crs)
    payload = OsmSpatialPayload(graph, buildings, spots, manifest)
    return SpatialDataset(
        payload=payload,
        source=manifest.source,
        acquired_at=manifest.acquired_at_utc,
        scope=_scope_text(manifest),
        crs=manifest.crs,
    )


@dataclass(frozen=True)
class PreparedOsmDataSource:
    directory: Path

    def load(self, start: GeoPoint, destination: GeoPoint) -> SpatialDataset:
        dataset = load_prepared_dataset(self.directory)
        validate_dataset_scope(dataset, start, destination)
        return dataset


def validate_dataset_scope(
    dataset: SpatialDataset, start: GeoPoint, destination: GeoPoint
) -> None:
    manifest = dataset.payload.manifest
    center = GeoPoint(**manifest.center)
    for label, point in (("start", start), ("destination", destination)):
        if _distance_m(center, point) > manifest.radius_m:
            raise ValueError(f"{label} is outside the prepared dataset scope")


def prepare_osm_dataset(
    config: OsmPreparationConfig,
    destination: str | Path,
    *,
    cache_dir: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Explicit online preprocessing entry point used by the CLI."""
    if cache_dir is not None:
        ox.settings.use_cache = True
        ox.settings.cache_folder = str(Path(cache_dir))
    payload = fetch_osm_data(config)
    return save_prepared_dataset(payload, destination, overwrite=overwrite)


def _make_manifest(
    config: OsmPreparationConfig,
    acquired_at: str,
    graph: nx.MultiDiGraph,
    buildings: gpd.GeoDataFrame,
    spots: gpd.GeoDataFrame,
) -> PreparedDatasetManifest:
    return PreparedDatasetManifest(
        schema_version=SCHEMA_VERSION,
        source="OpenStreetMap via OSMnx",
        attribution=OSM_ATTRIBUTION,
        copyright_url=OSM_COPYRIGHT_URL,
        acquired_at_utc=acquired_at,
        source_timestamp_note=(
            "acquired_at_utc records this preparation request; when the OSMnx "
            "HTTP cache is used, the source response may be older"
        ),
        center=asdict(config.center),
        radius_m=config.radius_m,
        crs=config.projected_crs,
        default_building_height_m=config.default_building_height_m,
        files={
            "graph": GRAPH_FILE,
            "buildings": BUILDINGS_FILE,
            "spots": SPOTS_FILE,
        },
        sha256={},
        counts={
            "road_nodes": graph.number_of_nodes(),
            "road_edges": graph.number_of_edges(),
            "buildings": len(buildings),
            "spots": len(spots),
        },
    )


def _validate_loaded_crs(
    graph: nx.MultiDiGraph,
    buildings: gpd.GeoDataFrame,
    spots: gpd.GeoDataFrame,
    expected: str,
) -> None:
    values: dict[str, Any] = {
        "graph": graph.graph.get("crs"),
        "buildings": buildings.crs,
        "spots": spots.crs,
    }
    mismatched = [name for name, value in values.items() if str(value) != expected]
    if mismatched:
        raise ValueError(f"prepared CRS mismatch: {', '.join(mismatched)}")


def _scope_text(manifest: PreparedDatasetManifest) -> str:
    return (
        f"center={manifest.center['latitude']},{manifest.center['longitude']};"
        f" radius_m={manifest.radius_m}"
    )


def _distance_m(a: GeoPoint, b: GeoPoint) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(b.longitude - a.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(haversine))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
