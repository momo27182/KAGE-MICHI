"""Convert local PLATEAU CityGML buildings into verified offline artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from time import perf_counter
from typing import BinaryIO, Iterator
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import LinearRing, Point, Polygon
from shapely.ops import unary_union

from ..models import GeoPoint


SCHEMA_VERSION = 1
BUILDINGS_FILE = "buildings.gpkg"
MANIFEST_FILE = "manifest.json"
SOURCE_NAME = "Project PLATEAU 和歌山市2023年度 CityGML v4"
DATASET_ID = "plateau-30201-wakayama-shi-2023"
DATASET_URL = (
    "https://www.geospatial.jp/ckan/dataset/"
    "plateau-30201-wakayama-shi-2023"
)
DOWNLOAD_URL = (
    "https://assets.cms.plateau.reearth.io/assets/"
    "33/e43850-ce18-4bcb-9a8b-88bf2eb8f2a3/"
    "30201_wakayama-shi_city_2023_citygml_2_op.zip"
)
ATTRIBUTION = (
    "出典：和歌山市「3D都市モデル（Project PLATEAU）和歌山市"
    "（2023年度）」、国土交通省Project PLATEAU / "
    "G空間情報センター、KAGE-MICHIで加工"
)


@dataclass(frozen=True)
class PlateauPreparationConfig:
    center: GeoPoint = GeoPoint(34.2325, 135.1917)
    radius_m: int = 1_700
    projected_crs: str = "EPSG:6676"
    mesh_codes: tuple[str, ...] = ()
    source_url: str = DOWNLOAD_URL
    source_etag: str | None = None
    source_acquired_at_utc: str | None = None

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        CRS.from_user_input(self.projected_crs)
        invalid = [code for code in self.mesh_codes if len(code) != 8 or not code.isdigit()]
        if invalid:
            raise ValueError(f"invalid third-level mesh code: {invalid[0]}")


@dataclass(frozen=True)
class PlateauManifest:
    schema_version: int
    source: str
    dataset_id: str
    dataset_url: str
    source_url: str
    source_etag: str | None
    source_acquired_at_utc: str | None
    source_bytes: int
    attribution: str
    prepared_at_utc: str
    center: dict[str, float]
    radius_m: int
    selected_mesh_codes: list[str]
    source_crs: list[str]
    projected_crs: str
    files: dict[str, str]
    input_sha256: str
    output_sha256: dict[str, str]
    semantic_sha256: str
    counts: dict[str, int]
    metrics: dict[str, float | int]

    @classmethod
    def from_json(cls, path: Path) -> "PlateauManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest = cls(**raw)
        if manifest.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported PLATEAU prepared schema: {manifest.schema_version}"
            )
        return manifest


@dataclass(frozen=True)
class PreparedPlateauBuildings:
    buildings: gpd.GeoDataFrame
    manifest: PlateauManifest


def third_mesh_code(latitude: float, longitude: float) -> str:
    """Return the Japanese third-level mesh code containing one coordinate."""
    if not (-90 <= latitude <= 90 and 100 <= longitude < 180):
        raise ValueError("coordinate is outside the supported Japanese mesh range")
    lat_index = math.floor(latitude * 120)
    lon_index = math.floor((longitude - 100) * 80)
    first_lat, lat_remainder = divmod(lat_index, 80)
    first_lon, lon_remainder = divmod(lon_index, 80)
    second_lat, third_lat = divmod(lat_remainder, 10)
    second_lon, third_lon = divmod(lon_remainder, 10)
    return (
        f"{first_lat:02d}{first_lon:02d}"
        f"{second_lat}{second_lon}{third_lat}{third_lon}"
    )


def mesh_codes_for_radius(center: GeoPoint, radius_m: int) -> tuple[str, ...]:
    """Return all third-level meshes intersecting a conservative radius bbox."""
    lat_delta = radius_m / 111_320
    lon_delta = radius_m / (111_320 * math.cos(math.radians(center.latitude)))
    min_lat = center.latitude - lat_delta
    max_lat = center.latitude + lat_delta
    min_lon = center.longitude - lon_delta
    max_lon = center.longitude + lon_delta
    lat_start = math.floor(min_lat * 120)
    lat_end = math.floor(max_lat * 120)
    lon_start = math.floor((min_lon - 100) * 80)
    lon_end = math.floor((max_lon - 100) * 80)
    codes = {
        _mesh_code_from_indices(lat_index, lon_index)
        for lat_index in range(lat_start, lat_end + 1)
        for lon_index in range(lon_start, lon_end + 1)
    }
    return tuple(sorted(codes))


def prepare_plateau_buildings(
    source: str | Path,
    destination: str | Path,
    config: PlateauPreparationConfig,
    *,
    overwrite: bool = False,
) -> Path:
    """Parse selected local CityGML files, project, filter, and persist them."""
    source_path = Path(source)
    output = Path(destination)
    targets = [output / BUILDINGS_FILE, output / MANIFEST_FILE]
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "prepared PLATEAU dataset already exists: "
            + ", ".join(path.name for path in existing)
        )

    selected_meshes = config.mesh_codes or mesh_codes_for_radius(
        config.center, config.radius_m
    )
    started_at = datetime.now(timezone.utc)
    parse_started = perf_counter()
    source_frames: list[gpd.GeoDataFrame] = []
    source_crs: set[str] = set()
    parsed_files = 0
    for name, stream in _citygml_streams(source_path, set(selected_meshes)):
        frame, crs_name = parse_citygml_buildings(stream, source_name=name)
        parsed_files += 1
        source_crs.add(crs_name)
        if not frame.empty:
            source_frames.append(frame.to_crs(config.projected_crs))
    if parsed_files == 0:
        raise ValueError("no matching PLATEAU building CityGML files found")
    if not source_frames:
        raise ValueError("selected PLATEAU CityGML files contain no valid buildings")

    buildings = gpd.GeoDataFrame(
        pd.concat(source_frames, ignore_index=True),
        geometry="geometry",
        crs=config.projected_crs,
    )
    buildings = _deduplicate_and_filter(buildings, config)
    if buildings.empty:
        raise ValueError("no PLATEAU buildings intersect the configured scope")
    buildings = buildings.sort_values(
        ["building_id", "source_mesh"], kind="stable"
    ).reset_index(drop=True)
    semantic_sha = _semantic_sha256(buildings)
    parse_seconds = perf_counter() - parse_started

    output.mkdir(parents=True, exist_ok=True)
    buildings_path = output / BUILDINGS_FILE
    write_started = perf_counter()
    buildings.to_file(buildings_path, driver="GPKG", layer="buildings", index=False)
    write_seconds = perf_counter() - write_started
    hash_started = perf_counter()
    input_sha = _input_sha256(source_path)
    output_sha = _sha256(buildings_path)
    hash_seconds = perf_counter() - hash_started
    finished_at = datetime.now(timezone.utc)
    manifest = PlateauManifest(
        schema_version=SCHEMA_VERSION,
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        dataset_url=DATASET_URL,
        source_url=config.source_url,
        source_etag=config.source_etag,
        source_acquired_at_utc=config.source_acquired_at_utc,
        source_bytes=_source_bytes(source_path),
        attribution=ATTRIBUTION,
        prepared_at_utc=finished_at.isoformat(),
        center=asdict(config.center),
        radius_m=config.radius_m,
        selected_mesh_codes=list(selected_meshes),
        source_crs=sorted(source_crs),
        projected_crs=config.projected_crs,
        files={"buildings": BUILDINGS_FILE},
        input_sha256=input_sha,
        output_sha256={"buildings": output_sha},
        semantic_sha256=semantic_sha,
        counts={
            "citygml_files": parsed_files,
            "buildings": len(buildings),
            "missing_height": int(buildings["height_m"].isna().sum()),
            "lod2_buildings": int(buildings["has_lod2"].sum()),
        },
        metrics={
            "preparation_seconds": round(
                (finished_at - started_at).total_seconds(), 6
            ),
            "parse_filter_seconds": round(parse_seconds, 6),
            "write_seconds": round(write_seconds, 6),
            "hash_seconds": round(hash_seconds, 6),
            "peak_memory_bytes": _peak_memory_bytes(),
            "output_bytes": buildings_path.stat().st_size,
        },
    )
    (output / MANIFEST_FILE).write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def load_prepared_plateau_buildings(
    directory: str | Path,
) -> PreparedPlateauBuildings:
    """Load and verify local prepared PLATEAU buildings without network access."""
    root = Path(directory)
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise FileNotFoundError(f"PLATEAU manifest not found: {manifest_path}")
    manifest = PlateauManifest.from_json(manifest_path)
    buildings_path = root / manifest.files["buildings"]
    if not buildings_path.is_file():
        raise FileNotFoundError(
            f"prepared PLATEAU buildings not found: {buildings_path}"
        )
    if _sha256(buildings_path) != manifest.output_sha256.get("buildings"):
        raise ValueError("prepared PLATEAU checksum mismatch: buildings")
    buildings = gpd.read_file(buildings_path, layer="buildings")
    if str(buildings.crs) != manifest.projected_crs:
        raise ValueError("prepared PLATEAU CRS mismatch: buildings")
    if _semantic_sha256(buildings) != manifest.semantic_sha256:
        raise ValueError("prepared PLATEAU semantic checksum mismatch")
    return PreparedPlateauBuildings(buildings, manifest)


def parse_citygml_buildings(
    stream: BinaryIO,
    *,
    source_name: str = "<stream>",
) -> tuple[gpd.GeoDataFrame, str]:
    """Stream one CityGML document and extract LOD1 building footprints."""
    rows: list[dict[str, object]] = []
    srs_name: str | None = None
    try:
        events = ET.iterparse(stream, events=("end",))
        for _, element in events:
            local = _local_name(element.tag)
            if local == "Envelope" and srs_name is None:
                srs_name = element.attrib.get("srsName")
            elif local == "Building":
                if not srs_name:
                    raise ValueError(
                        f"CityGML CRS is missing before buildings: {source_name}"
                    )
                row = _building_row(element, srs_name, source_name)
                if row is not None:
                    rows.append(row)
                element.clear()
    except ET.ParseError as error:
        raise ValueError(f"invalid CityGML XML: {source_name}") from error
    if not srs_name:
        raise ValueError(f"CityGML CRS is missing: {source_name}")
    source_crs = _horizontal_crs(srs_name)
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=source_crs)
    return frame, srs_name


def _building_row(
    building: ET.Element, srs_name: str, source_name: str
) -> dict[str, object] | None:
    building_id = next(
        (value for key, value in building.attrib.items() if _local_name(key) == "id"),
        None,
    )
    if not building_id:
        raise ValueError(f"PLATEAU building is missing gml:id: {source_name}")
    solids = _descendants_named(building, "lod1Solid")
    polygons: list[tuple[Polygon, list[float]]] = []
    for solid in solids:
        polygons.extend(_polygons_from_element(solid, srs_name))
    if not polygons:
        return None
    z_values = [z for _, values in polygons for z in values]
    if not z_values:
        return None
    bottom = min(z_values)
    top = max(z_values)
    tolerance = max(0.01, (top - bottom) * 0.001)
    bottom_polygons = [
        polygon
        for polygon, values in polygons
        if values and max(abs(value - bottom) for value in values) <= tolerance
    ]
    if not bottom_polygons:
        min_polygon = min(polygons, key=lambda item: sum(item[1]) / len(item[1]))
        bottom_polygons = [min_polygon[0]]
    footprint = unary_union(bottom_polygons)
    if footprint.is_empty:
        return None
    if not footprint.is_valid:
        footprint = footprint.buffer(0)
    measured = _first_float(building, "measuredHeight")
    height_type = _first_text(building, "lod1HeightType")
    return {
        "building_id": building_id,
        "source_mesh": _mesh_from_name(source_name),
        "lod": 1,
        "has_lod2": bool(_descendants_named(building, "lod2Solid")),
        "bottom_z_m": bottom,
        "top_z_m": top,
        "height_m": top - bottom if top > bottom else None,
        "measured_height_m": measured,
        "lod1_height_type": height_type,
        "geometry": footprint,
    }


def _polygons_from_element(
    element: ET.Element, srs_name: str
) -> list[tuple[Polygon, list[float]]]:
    result: list[tuple[Polygon, list[float]]] = []
    for polygon_element in _descendants_named(element, "Polygon"):
        exterior: list[tuple[float, float, float]] | None = None
        interiors: list[list[tuple[float, float, float]]] = []
        for boundary in list(polygon_element):
            boundary_name = _local_name(boundary.tag)
            if boundary_name not in {"exterior", "interior"}:
                continue
            points = _points_from_boundary(boundary, srs_name)
            if len(points) < 4:
                continue
            if boundary_name == "exterior":
                exterior = points
            else:
                interiors.append(points)
        if exterior is None:
            continue
        shell = [(x, y) for x, y, _ in exterior]
        holes = [[(x, y) for x, y, _ in ring] for ring in interiors]
        if not LinearRing(shell).is_valid:
            continue
        polygon = Polygon(shell, holes)
        if not polygon.is_empty:
            result.append((polygon, [z for _, _, z in exterior]))
    return result


def _points_from_boundary(
    boundary: ET.Element, srs_name: str
) -> list[tuple[float, float, float]]:
    pos_lists = _descendants_named(boundary, "posList")
    if pos_lists:
        element = pos_lists[0]
        values = [float(value) for value in (element.text or "").split()]
        dimension = int(element.attrib.get("srsDimension", "3"))
        if dimension != 3 or len(values) % 3:
            raise ValueError("PLATEAU polygon coordinates must be 3-dimensional")
        return [
            (*_normalise_xy(srs_name, values[i], values[i + 1]), values[i + 2])
            for i in range(0, len(values), 3)
        ]
    points: list[tuple[float, float, float]] = []
    for element in _descendants_named(boundary, "pos"):
        values = [float(value) for value in (element.text or "").split()]
        if len(values) != 3:
            raise ValueError("PLATEAU polygon coordinates must be 3-dimensional")
        x, y = _normalise_xy(srs_name, values[0], values[1])
        points.append((x, y, values[2]))
    return points


def _deduplicate_and_filter(
    buildings: gpd.GeoDataFrame, config: PlateauPreparationConfig
) -> gpd.GeoDataFrame:
    buildings = buildings.drop_duplicates(subset=["building_id"], keep="first")
    center = gpd.GeoSeries(
        [Point(config.center.longitude, config.center.latitude)], crs="EPSG:4326"
    ).to_crs(config.projected_crs).iloc[0]
    scope = center.buffer(config.radius_m)
    return buildings[buildings.geometry.intersects(scope)].copy()


def _citygml_streams(
    source: Path, selected_meshes: set[str]
) -> Iterator[tuple[str, BinaryIO]]:
    if source.is_file() and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if _is_selected_building_gml(name, selected_meshes)
            )
            for name in names:
                with archive.open(name) as member:
                    yield name, member
        return
    if source.is_dir():
        for path in sorted(source.rglob("*.gml")):
            if _is_selected_building_gml(path.name, selected_meshes):
                with path.open("rb") as stream:
                    yield str(path), stream
        return
    raise FileNotFoundError(f"PLATEAU CityGML source not found: {source}")


def _is_selected_building_gml(name: str, selected_meshes: set[str]) -> bool:
    filename = Path(name).name
    return (
        filename.lower().endswith(".gml")
        and "_bldg_" in filename.lower()
        and (not selected_meshes or filename[:8] in selected_meshes)
    )


def _input_sha256(source: Path) -> str:
    if source.is_file():
        return _sha256(source)
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.gml")):
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(_sha256(path).encode())
    return digest.hexdigest()


def _source_bytes(source: Path) -> int:
    if source.is_file():
        return source.stat().st_size
    return sum(path.stat().st_size for path in source.rglob("*.gml"))


def _peak_memory_bytes() -> int:
    """Return the process peak working set without adding a runtime dependency."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            return int(counters.PeakWorkingSetSize)
        return 0
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if os.uname().sysname == "Darwin" else peak * 1024)
    except (ImportError, AttributeError):
        return 0


def _semantic_sha256(buildings: gpd.GeoDataFrame) -> str:
    digest = hashlib.sha256()
    columns = [
        "building_id",
        "source_mesh",
        "lod",
        "has_lod2",
        "bottom_z_m",
        "top_z_m",
        "height_m",
        "measured_height_m",
        "lod1_height_type",
    ]
    ordered = buildings.sort_values(["building_id", "source_mesh"], kind="stable")
    for _, row in ordered.iterrows():
        values = [_json_scalar(row.get(column)) for column in columns]
        values.append(row.geometry.normalize().wkb_hex)
        digest.update(
            json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _json_scalar(value: object) -> object:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _horizontal_crs(srs_name: str) -> CRS:
    try:
        crs = CRS.from_user_input(srs_name)
    except Exception as error:
        raise ValueError(f"unsupported CityGML CRS: {srs_name}") from error
    return crs.to_2d() if crs.is_compound else crs


def _normalise_xy(srs_name: str, first: float, second: float) -> tuple[float, float]:
    crs = CRS.from_user_input(srs_name)
    axes = crs.axis_info
    if len(axes) >= 2 and axes[0].direction.lower() in {"north", "south"}:
        return second, first
    return first, second


def _mesh_code_from_indices(lat_index: int, lon_index: int) -> str:
    first_lat, lat_remainder = divmod(lat_index, 80)
    first_lon, lon_remainder = divmod(lon_index, 80)
    second_lat, third_lat = divmod(lat_remainder, 10)
    second_lon, third_lon = divmod(lon_remainder, 10)
    return (
        f"{first_lat:02d}{first_lon:02d}"
        f"{second_lat}{second_lon}{third_lat}{third_lon}"
    )


def _descendants_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element.iter() if _local_name(item.tag) == name]


def _first_float(element: ET.Element, name: str) -> float | None:
    text = _first_text(element, name)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_text(element: ET.Element, name: str) -> str | None:
    items = _descendants_named(element, name)
    if not items or not items[0].text:
        return None
    return items[0].text.strip() or None


def _mesh_from_name(name: str) -> str:
    filename = Path(name).name
    return filename[:8] if len(filename) >= 8 and filename[:8].isdigit() else ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
