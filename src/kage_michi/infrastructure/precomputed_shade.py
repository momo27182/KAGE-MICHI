"""Generate and validate time-indexed road shade ratios offline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from time import perf_counter
from typing import Callable

import networkx as nx
import numpy as np
import shapely
from shapely.geometry import LineString

from ..data import SpatialDataset
from ..models import GeoPoint
from ..shadows import ShadowResult
from .edge_shade import normalize_edge_geometry
from .osm_prepared import load_prepared_dataset
from .plateau_prepared import load_prepared_plateau_buildings
from .shadow_calculator import BuildingShadowCalculator


SCHEMA_VERSION = 1
SHADE_MODEL_VERSION = "convex-hull-v1"
DATA_FILE = "shade-ratios.npz"
MANIFEST_FILE = "manifest.json"
NIGHTTIME_SEMANTICS = (
    "daylight=false and shade_ratio=1.0 means zero direct solar exposure; "
    "it must be presented as nighttime, not as building shade"
)


@dataclass(frozen=True)
class ShadeTimeRange:
    start: datetime
    end: datetime
    interval_minutes: int = 5
    sample_spacing_m: float = 5.0

    def __post_init__(self) -> None:
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("shade time range must include timezone information")
        if self.end < self.start:
            raise ValueError("shade time range end must not precede start")
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        if self.sample_spacing_m <= 0:
            raise ValueError("sample_spacing_m must be positive")

    def timestamps(self) -> tuple[datetime, ...]:
        step = timedelta(minutes=self.interval_minutes)
        values = []
        current = self.start
        while current <= self.end:
            values.append(current)
            current += step
        return tuple(values)


@dataclass(frozen=True)
class ShadeArtifactManifest:
    schema_version: int
    shade_model_version: str
    prepared_at_utc: str
    region: str
    start: str
    end: str
    timezone: str
    interval_minutes: int
    sample_spacing_m: float
    projected_crs: str
    source_sha256: dict[str, str]
    files: dict[str, str]
    output_sha256: dict[str, str]
    semantic_sha256: str
    counts: dict[str, int]
    nighttime_semantics: str
    metrics: dict[str, float | int]

    @classmethod
    def from_json(cls, path: Path) -> "ShadeArtifactManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest = cls(**raw)
        if manifest.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported shade artifact schema: {manifest.schema_version}"
            )
        if manifest.shade_model_version != SHADE_MODEL_VERSION:
            raise ValueError(
                "unsupported shade model version: "
                f"{manifest.shade_model_version}"
            )
        return manifest


@dataclass(frozen=True)
class PreparedShadeRatios:
    manifest: ShadeArtifactManifest
    timestamps: tuple[str, ...]
    daylight: np.ndarray
    solar_altitude_deg: np.ndarray
    edge_u: tuple[str, ...]
    edge_v: tuple[str, ...]
    edge_key: tuple[str, ...]
    ratios: np.ndarray

    def ratios_at(self, at: datetime) -> np.ndarray:
        if at.utcoffset() is None:
            raise ValueError("requested shade time must include timezone information")
        key = at.isoformat()
        try:
            index = self.timestamps.index(key)
        except ValueError as error:
            raise KeyError(f"shade ratios are not available for {key}") from error
        return self.ratios[index].copy()


def generate_shade_artifact(
    graph: nx.MultiDiGraph,
    shadow_at: Callable[[datetime], ShadowResult],
    destination: str | Path,
    time_range: ShadeTimeRange,
    source_sha256: dict[str, str],
    *,
    region: str,
) -> Path:
    """Generate a complete artifact in a temporary sibling, then publish it."""
    output = Path(destination)
    if output.exists():
        raise FileExistsError(f"shade artifact already exists: {output}")
    crs = graph.graph.get("crs")
    if crs is None:
        raise ValueError("road graph must define a projected CRS")
    if not source_sha256 or any(not value for value in source_sha256.values()):
        raise ValueError("source checksums must not be empty")
    if not region.strip():
        raise ValueError("region must not be empty")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    started = perf_counter()
    try:
        edge_u, edge_v, edge_key, points, point_edge, sample_counts = _edge_samples(
            graph, time_range.sample_spacing_m
        )
        timestamps = time_range.timestamps()
        ratios = np.empty((len(timestamps), len(edge_u)), dtype=np.float32)
        daylight = np.empty(len(timestamps), dtype=np.bool_)
        altitudes = np.empty(len(timestamps), dtype=np.float32)
        for index, timestamp in enumerate(timestamps):
            shadow = shadow_at(timestamp)
            altitude = float(shadow.solar_altitude_deg)
            altitudes[index] = altitude
            daylight[index] = altitude > 0
            if altitude <= 0:
                ratios[index].fill(1.0)
            elif shadow.geometry is None or shadow.geometry.is_empty:
                ratios[index].fill(0.0)
            else:
                covered = shapely.covered_by(points, shadow.geometry).astype(np.float32)
                shaded = np.bincount(
                    point_edge, weights=covered, minlength=len(edge_u)
                )
                ratios[index] = shaded / sample_counts

        data_path = temporary / DATA_FILE
        np.savez_compressed(
            data_path,
            timestamps=np.asarray([value.isoformat() for value in timestamps]),
            daylight=daylight,
            solar_altitude_deg=altitudes,
            edge_u=np.asarray(edge_u),
            edge_v=np.asarray(edge_v),
            edge_key=np.asarray(edge_key),
            ratios=ratios,
        )
        validation_load_started = perf_counter()
        with np.load(data_path, allow_pickle=False) as archive:
            if archive["ratios"].shape != ratios.shape:
                raise ValueError("written shade ratio shape does not match input")
        validation_load_seconds = perf_counter() - validation_load_started
        finished = datetime.now(timezone.utc)
        manifest = ShadeArtifactManifest(
            schema_version=SCHEMA_VERSION,
            shade_model_version=SHADE_MODEL_VERSION,
            prepared_at_utc=finished.isoformat(),
            region=region.strip(),
            start=time_range.start.isoformat(),
            end=time_range.end.isoformat(),
            timezone=str(time_range.start.tzinfo),
            interval_minutes=time_range.interval_minutes,
            sample_spacing_m=time_range.sample_spacing_m,
            projected_crs=str(crs),
            source_sha256=dict(sorted(source_sha256.items())),
            files={"ratios": DATA_FILE},
            output_sha256={"ratios": _sha256(data_path)},
            semantic_sha256=_semantic_sha256(
                timestamps, daylight, altitudes, edge_u, edge_v, edge_key, ratios
            ),
            counts={
                "timestamps": len(timestamps),
                "daylight_timestamps": int(daylight.sum()),
                "edges": len(edge_u),
                "samples": len(points),
                "values": int(ratios.size),
            },
            nighttime_semantics=NIGHTTIME_SEMANTICS,
            metrics={
                "generation_seconds": round(perf_counter() - started, 6),
                "peak_memory_bytes": _peak_memory_bytes(),
                "output_bytes": data_path.stat().st_size,
                "validation_load_seconds": round(validation_load_seconds, 6),
            },
        )
        (temporary / MANIFEST_FILE).write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
        return output
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def generate_prepared_shade_artifact(
    osm_directory: str | Path,
    plateau_directory: str | Path,
    destination: str | Path,
    time_range: ShadeTimeRange,
    *,
    center: GeoPoint = GeoPoint(34.2325, 135.1917),
) -> Path:
    """Generate from checksum-verified prepared OSM and PLATEAU artifacts."""
    osm = load_prepared_dataset(osm_directory)
    plateau = load_prepared_plateau_buildings(plateau_directory)
    if str(osm.payload.graph.graph.get("crs")) != plateau.manifest.projected_crs:
        raise ValueError("OSM road and PLATEAU building CRS must match")
    buildings = plateau.buildings[["height_m", "geometry"]].rename(
        columns={"height_m": "height"}
    )
    buildings = buildings.explode(index_parts=False, ignore_index=True)
    buildings = buildings[buildings.geometry.geom_type == "Polygon"].reset_index(
        drop=True
    )
    payload = type(
        "PreparedShadePayload",
        (),
        {"buildings": buildings, "manifest": plateau.manifest},
    )()
    shadow_dataset = SpatialDataset(
        payload=payload,
        source="PLATEAU LOD1",
        acquired_at=plateau.manifest.source_acquired_at_utc or "unknown",
        scope=osm.scope,
        crs=plateau.manifest.projected_crs,
    )
    calculator = BuildingShadowCalculator(center=center)
    return generate_shade_artifact(
        osm.payload.graph,
        lambda timestamp: calculator.calculate(shadow_dataset, timestamp),
        destination,
        time_range,
        {
            "osm_graph": osm.payload.manifest.sha256["graph"],
            "plateau_buildings": plateau.manifest.output_sha256["buildings"],
        },
        region=str(osm.scope),
    )


def load_shade_artifact(
    directory: str | Path,
    *,
    expected_source_sha256: dict[str, str] | None = None,
) -> PreparedShadeRatios:
    """Load and fully validate one offline shade artifact."""
    root = Path(directory)
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise FileNotFoundError(f"shade manifest not found: {manifest_path}")
    manifest = ShadeArtifactManifest.from_json(manifest_path)
    if manifest.nighttime_semantics != NIGHTTIME_SEMANTICS:
        raise ValueError("shade artifact nighttime semantics mismatch")
    if expected_source_sha256 is not None and dict(
        sorted(expected_source_sha256.items())
    ) != manifest.source_sha256:
        raise ValueError("shade artifact source version mismatch")
    data_path = root / manifest.files["ratios"]
    if not data_path.is_file():
        raise FileNotFoundError(f"shade ratios not found: {data_path}")
    if _sha256(data_path) != manifest.output_sha256.get("ratios"):
        raise ValueError("shade artifact checksum mismatch: ratios")

    with np.load(data_path, allow_pickle=False) as archive:
        required = {
            "timestamps",
            "daylight",
            "solar_altitude_deg",
            "edge_u",
            "edge_v",
            "edge_key",
            "ratios",
        }
        if set(archive.files) != required:
            raise ValueError("shade artifact arrays are missing or unexpected")
        timestamps = tuple(str(value) for value in archive["timestamps"])
        daylight = archive["daylight"].astype(np.bool_, copy=True)
        altitudes = archive["solar_altitude_deg"].astype(np.float32, copy=True)
        edge_u = tuple(str(value) for value in archive["edge_u"])
        edge_v = tuple(str(value) for value in archive["edge_v"])
        edge_key = tuple(str(value) for value in archive["edge_key"])
        ratios = archive["ratios"].astype(np.float32, copy=True)

    _validate_arrays(manifest, timestamps, daylight, altitudes, edge_u, edge_v, edge_key, ratios)
    expected_semantic = _semantic_sha256(
        tuple(datetime.fromisoformat(value) for value in timestamps),
        daylight,
        altitudes,
        edge_u,
        edge_v,
        edge_key,
        ratios,
    )
    if expected_semantic != manifest.semantic_sha256:
        raise ValueError("shade artifact semantic checksum mismatch")
    return PreparedShadeRatios(
        manifest, timestamps, daylight, altitudes, edge_u, edge_v, edge_key, ratios
    )


def _edge_samples(
    graph: nx.MultiDiGraph, spacing_m: float
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    ordered = sorted(
        graph.edges(keys=True, data=True),
        key=lambda item: (str(item[0]), str(item[1]), str(item[2])),
    )
    edge_u: list[str] = []
    edge_v: list[str] = []
    edge_key: list[str] = []
    points = []
    point_edge = []
    sample_counts = []
    for edge_index, (u, v, key, data) in enumerate(ordered):
        geometry = data.get("geometry")
        if geometry is None:
            geometry = LineString(
                [
                    (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
                    (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
                ]
            )
        line = normalize_edge_geometry(geometry)
        count = max(1, int(np.ceil(line.length / spacing_m)))
        edge_u.append(str(u))
        edge_v.append(str(v))
        edge_key.append(str(key))
        sample_counts.append(count)
        for sample_index in range(count):
            points.append(
                line.interpolate((sample_index + 0.5) / count, normalized=True)
            )
            point_edge.append(edge_index)
    identities = set(zip(edge_u, edge_v, edge_key))
    if len(identities) != len(edge_u):
        raise ValueError("road graph contains duplicate stable edge keys")
    return (
        tuple(edge_u),
        tuple(edge_v),
        tuple(edge_key),
        np.asarray(points, dtype=object),
        np.asarray(point_edge, dtype=np.int64),
        np.asarray(sample_counts, dtype=np.float32),
    )


def _validate_arrays(
    manifest: ShadeArtifactManifest,
    timestamps: tuple[str, ...],
    daylight: np.ndarray,
    altitudes: np.ndarray,
    edge_u: tuple[str, ...],
    edge_v: tuple[str, ...],
    edge_key: tuple[str, ...],
    ratios: np.ndarray,
) -> None:
    time_count = manifest.counts["timestamps"]
    edge_count = manifest.counts["edges"]
    if not (
        len(timestamps) == daylight.size == altitudes.size == time_count
        and len(edge_u) == len(edge_v) == len(edge_key) == edge_count
        and ratios.shape == (time_count, edge_count)
        and ratios.dtype == np.float32
    ):
        raise ValueError("shade artifact shape or dtype mismatch")
    if not np.isfinite(ratios).all() or np.any((ratios < 0) | (ratios > 1)):
        raise ValueError("shade ratios must be finite values from 0 to 1")
    if np.any(ratios[~daylight] != np.float32(1.0)):
        raise ValueError("nighttime shade ratios do not match the declared semantics")
    if len(set(zip(edge_u, edge_v, edge_key))) != edge_count:
        raise ValueError("shade artifact contains duplicate stable edge keys")
    parsed = tuple(datetime.fromisoformat(value) for value in timestamps)
    if any(value.utcoffset() is None for value in parsed):
        raise ValueError("shade timestamps must include timezone information")
    if tuple(sorted(parsed)) != parsed or len(set(parsed)) != len(parsed):
        raise ValueError("shade timestamps must be unique and ordered")


def _semantic_sha256(
    timestamps: tuple[datetime, ...],
    daylight: np.ndarray,
    altitudes: np.ndarray,
    edge_u: tuple[str, ...],
    edge_v: tuple[str, ...],
    edge_key: tuple[str, ...],
    ratios: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    for value in timestamps:
        digest.update(value.isoformat().encode())
        digest.update(b"\n")
    digest.update(np.ascontiguousarray(daylight, dtype=np.bool_).tobytes())
    digest.update(np.ascontiguousarray(altitudes, dtype="<f4").tobytes())
    for values in zip(edge_u, edge_v, edge_key):
        digest.update(json.dumps(values, separators=(",", ":")).encode())
        digest.update(b"\n")
    digest.update(np.ascontiguousarray(ratios, dtype="<f4").tobytes())
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _peak_memory_bytes() -> int:
    if os.name != "nt":
        return 0
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
    if psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return int(counters.PeakWorkingSetSize)
    return 0
